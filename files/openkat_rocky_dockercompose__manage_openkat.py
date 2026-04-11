#!/usr/bin/env python3
"""
OpenKAT Management Script

This script manages OpenKAT superusers, organizations, and OOI objects
in a Docker Compose deployment via docker exec commands.
"""

import argparse
import subprocess
import sys
from pathlib import Path


class DjangoSuperuserManager:
    """Manages Django superusers in a Docker container."""

    def __init__(self, compose_file, service_name, manage_py_path):
        """
        Initialize the manager.

        Args:
            compose_file: Path to docker-compose.yml file
            service_name: Name of the service in docker-compose
            manage_py_path: Path to manage.py inside the container
        """
        self.compose_file = compose_file
        self.service_name = service_name
        self.manage_py_path = manage_py_path
        self.container_id = None

    def get_container_id(self):
        """
        Get the container ID for the specified service.

        Returns:
            str: Container ID

        Raises:
            RuntimeError: If container cannot be found
        """
        if self.container_id:
            return self.container_id

        try:
            cmd = [
                "docker", "compose",
                "-f", self.compose_file,
                "ps"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Parse output to find the service
            for line in result.stdout.split('\n'):
                if self.service_name in line:
                    container_id = line.split()[0]
                    self.container_id = container_id
                    return container_id

            raise RuntimeError(f"Container for service '{self.service_name}' not found")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get container ID: {e.stderr}")

    def user_exists(self, email):
        """
        Check if a Django user exists by email.

        Args:
            email: Email address to check

        Returns:
            bool: True if user exists, False otherwise
        """
        try:
            container_id = self.get_container_id()

            # Normalize email to lowercase to handle custom user models like KATUser
            # that use LowercaseEmailField
            email_lower = email.lower()

            # Use Django shell to check if user exists
            # This handles both default User and custom user models
            escaped_email = email_lower.replace("'", "'\\''")
            check_cmd = """
from django.contrib.auth import get_user_model
User = get_user_model()
email = '{email}'
# Try exact match first
if User.objects.filter(email=email).exists():
    print('EXISTS')
# Try case-insensitive
elif User.objects.filter(email__iexact=email).exists():
    print('EXISTS_IEXACT')
else:
    # Debug: show all emails
    all_emails = list(User.objects.values_list('email', flat=True))
    print(f'NOT_EXISTS: All emails in DB: {{all_emails}}')
""".format(email=escaped_email)

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                check_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"Warning: Could not check if user exists: {result.stderr}", file=sys.stderr)
                return False

            output = result.stdout.strip()
            # Check if user exists - be careful! "NOT_EXISTS" contains "EXISTS" as substring
            if output.startswith("EXISTS"):
                return True
            else:
                return False

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def superuser_exists(self):
        """
        Check if any superuser accounts exist in the system.

        Returns:
            bool: True if any superuser exists, False otherwise
        """
        try:
            container_id = self.get_container_id()

            check_cmd = """
from django.contrib.auth import get_user_model
User = get_user_model()
superuser_count = User.objects.filter(is_superuser=True).count()
print('HAS_SUPERUSER' if superuser_count > 0 else 'NO_SUPERUSER')
"""

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                check_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"Warning: Could not check if superusers exist: {result.stderr}", file=sys.stderr)
                return False

            output = result.stdout.strip()
            if output.startswith("HAS_SUPERUSER"):
                return True
            else:
                return False

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def create_superuser(self, email, password, full_name=None, only_if_no_superuser_present=False):
        """
        Create a Django superuser in the container.

        Args:
            email: Email address for the superuser (used as identifier)
            password: Password for the superuser
            full_name: Full name (first_name and last_name separated by space)
            only_if_no_superuser_present: If True, only create if NO superuser accounts exist

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()
            print(f"Using container: {container_id}")

            # Normalize email to lowercase to handle custom user models like KATUser
            # that use LowercaseEmailField
            email_lower = email.lower()

            # KATUser uses email as USERNAME_FIELD, not username
            # full_name is a REQUIRED_FIELD for KATUser
            # Generate a default full_name from email if not provided
            if not full_name:
                full_name = email_lower.split('@')[0].title()

            # Check if any superuser already exists if requested
            if only_if_no_superuser_present:
                if self.superuser_exists():
                    print(f"Superuser account(s) already exist. Skipping creation.")
                    return True
                print(f"No superuser accounts exist. Creating first superuser...")

            # Prepare the createsuperuser command for KATUser
            # KATUser requires: email (USERNAME_FIELD) and full_name (REQUIRED_FIELD)
            # NO --username argument (KATUser uses email instead)
            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "createsuperuser",
                "--email", email_lower,
                "--full_name", full_name,
                "--noinput"
            ]

            # Execute the command with password from stdin
            # We'll use the --noinput flag and set the password afterward
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                if "already exists" in result.stderr:
                    print(f"Superuser with email '{email_lower}' already exists.")
                    return True
                raise RuntimeError(f"Failed to create superuser: {result.stderr}")

            # Set the password using a shell command
            # Escape special characters in password for shell safety
            # Set the password using a shell command with proper escaping
            set_password_cmd = """
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(email__iexact='{email}').first()
if u:
    u.set_password({password})
    u.save()
    print('Password set successfully')
else:
    print('User not found')
""".format(email=email_lower, password=repr(password))

            cmd_set_password = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                set_password_cmd
            ]

            result = subprocess.run(cmd_set_password, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to set password: {result.stderr}")

            if "User not found" in result.stdout:
                raise RuntimeError("Could not find user after creation")

            # Update full name if provided
            if full_name:
                parts = full_name.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""

                update_name_cmd = """
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(email__iexact={email}).first()
if u:
    u.first_name = {first_name}
    u.last_name = {last_name}
    u.save()
    print('Name updated')
else:
    print('User not found')
""".format(email=repr(email_lower), first_name=repr(first_name), last_name=repr(last_name))

                cmd_update_name = [
                    "docker", "exec",
                    container_id,
                    "python", self.manage_py_path,
                    "shell", "-c",
                    update_name_cmd
                ]

                result = subprocess.run(cmd_update_name, capture_output=True, text=True)

                if result.returncode != 0:
                    print(f"Warning: Could not update full name: {result.stderr}", file=sys.stderr)

            print(f"✓ Superuser created successfully with email '{email_lower}'")
            if full_name:
                print(f"  Full name: {full_name}")

            # Add superuser to existing organizations
            self._add_to_all_organizations(email_lower)

            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def _add_to_all_organizations(self, email):
        """
        Add a user to all existing OpenKAT organizations.

        If no organizations exist, this is a no-op (user will create one
        through the onboarding flow). If one or more organizations exist,
        the user is added as an active member with full clearance level.

        Args:
            email: Email address of the user (lowercase)
        """
        try:
            container_id = self.get_container_id()

            add_member_cmd = """
from django.contrib.auth import get_user_model
from tools.models import Organization, OrganizationMember
User = get_user_model()

user = User.objects.filter(email__iexact={email}).first()
if not user:
    print('USER_NOT_FOUND')
    raise SystemExit(1)

orgs = list(Organization.objects.all())
if not orgs:
    print('NO_ORGS')
else:
    for org in orgs:
        member, created = OrganizationMember.objects.get_or_create(
            user=user,
            organization=org,
            defaults={{
                'status': 'active',
                'blocked': False,
                'onboarded': True,
                'trusted_clearance_level': 4,
                'acknowledged_clearance_level': 4,
            }}
        )
        if not created:
            member.status = 'active'
            member.onboarded = True
            member.blocked = False
            member.trusted_clearance_level = 4
            member.acknowledged_clearance_level = 4
            member.save()
        action = 'created' if created else 'updated'
        print(f'MEMBER_{{action.upper()}}: {{org.name}} ({{org.code}})')
""".format(email=repr(email))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                add_member_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if "USER_NOT_FOUND" in result.stdout:
                print("  Warning: could not add to organizations (user not found)", file=sys.stderr)
                return

            if "NO_ORGS" in result.stdout:
                print("  No organizations exist yet (user will create one at first login)")
                return

            for line in result.stdout.strip().split('\n'):
                if line.startswith("MEMBER_"):
                    print(f"  {line}")

        except RuntimeError as e:
            print(f"  Warning: could not add to organizations: {e}", file=sys.stderr)

    def create_organization(self, name, code):
        """
        Create a new OpenKAT organization and add all existing superusers to it.

        Args:
            name: Display name for the organization
            code: Short unique code (lowercase slug)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            create_org_cmd = """
from django.contrib.auth import get_user_model
from tools.models import Organization, OrganizationMember
User = get_user_model()

# Check if org already exists
if Organization.objects.filter(code={code}).exists():
    print('ORG_EXISTS')
    raise SystemExit(1)

org = Organization.objects.create(name={name}, code={code})
print(f'ORG_CREATED: {{org.name}} ({{org.code}})')

# Add all superusers as members
for user in User.objects.filter(is_superuser=True):
    member, created = OrganizationMember.objects.get_or_create(
        user=user,
        organization=org,
        defaults={{
            'status': 'active',
            'blocked': False,
            'onboarded': True,
            'trusted_clearance_level': 4,
            'acknowledged_clearance_level': 4,
        }}
    )
    print(f'MEMBER_ADDED: {{user.email}}')
""".format(name=repr(name), code=repr(code))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                create_org_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if "ORG_EXISTS" in result.stdout:
                print(f"Error: Organization with code '{code}' already exists.", file=sys.stderr)
                return False

            if result.returncode != 0:
                raise RuntimeError(f"Failed to create organization: {result.stderr}")

            for line in result.stdout.strip().split('\n'):
                if line.startswith("ORG_CREATED"):
                    print(f"✓ Organization created: {line.split(': ', 1)[1]}")
                elif line.startswith("MEMBER_ADDED"):
                    print(f"  Added superuser: {line.split(': ', 1)[1]}")

            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def list_organizations(self):
        """List all organizations in the OpenKAT instance."""
        try:
            container_id = self.get_container_id()

            cmd_str = """
from tools.models import Organization, OrganizationMember
orgs = Organization.objects.all()
if not orgs:
    print('No organizations found')
else:
    for org in orgs:
        members = OrganizationMember.objects.filter(organization=org)
        member_list = ', '.join([m.user.email for m in members])
        print(f'{org.name} (code={org.code}) - members: {member_list or "none"}')
"""

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to list organizations: {result.stderr}")

            print("Organizations:")
            print(result.stdout)
            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def remove_organization(self, code, force=False):
        """
        Remove an OpenKAT organization and its memberships.

        Args:
            code: Organization code to remove
            force: Skip confirmation prompt

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            if not force:
                answer = input(f"Are you sure you want to remove organization '{code}' and all its memberships? [y/N] ")
                if answer.lower() != 'y':
                    print("Aborted.")
                    return False

            remove_org_cmd = """
from tools.models import Organization, OrganizationMember
from django.db import transaction

org = Organization.objects.filter(code={code}).first()
if not org:
    print('ORG_NOT_FOUND')
    raise SystemExit(1)

with transaction.atomic():
    member_count = OrganizationMember.objects.filter(organization=org).delete()[0]
    org_name = org.name
    org.delete()
    print(f'ORG_DELETED: {{org_name}} ({{member_count}} memberships removed)')
""".format(code=repr(code))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                remove_org_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if "ORG_NOT_FOUND" in result.stdout:
                print(f"Error: Organization with code '{code}' not found.", file=sys.stderr)
                return False

            if result.returncode != 0:
                raise RuntimeError(f"Failed to remove organization: {result.stderr}")

            for line in result.stdout.strip().split('\n'):
                if line.startswith("ORG_DELETED"):
                    print(f"✓ {line.split(': ', 1)[1]}")

            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def list_users(self):
        """List all users with their organization memberships. Superusers listed first."""
        try:
            container_id = self.get_container_id()

            cmd_str = """
from django.contrib.auth import get_user_model
from tools.models import OrganizationMember
User = get_user_model()
superusers = list(User.objects.filter(is_superuser=True).order_by('email'))
regular = list(User.objects.filter(is_superuser=False).order_by('email'))

if not superusers and not regular:
    print('NO_USERS')
else:
    for u in superusers:
        memberships = OrganizationMember.objects.filter(user=u)
        if memberships:
            orgs = ', '.join([f'{m.organization.name} ({m.organization.code})' for m in memberships])
        else:
            orgs = 'no organizations'
        print(f'SUPER: {u.email}  [{orgs}]')
    for u in regular:
        memberships = OrganizationMember.objects.filter(user=u)
        if memberships:
            orgs = ', '.join([f'{m.organization.name} ({m.organization.code})' for m in memberships])
        else:
            orgs = 'no organizations'
        print(f'USER: {u.email}  [{orgs}]')
"""

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to list users: {result.stderr}")

            if "NO_USERS" in result.stdout:
                print("No users found")
                return True

            print("Users:")
            for line in result.stdout.strip().split('\n'):
                if line.startswith("SUPER: "):
                    print(f"  [superuser]  {line[7:]}")
                elif line.startswith("USER: "):
                    print(f"  [user]       {line[6:]}")

            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def remove_superuser(self, email, force=False):
        """
        Remove a Django superuser by email.

        Args:
            email: Email address of the superuser to remove
            force: Skip confirmation prompt

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()
            print(f"Using container: {container_id}")

            # Normalize email to lowercase to handle custom user models like KATUser
            # that use LowercaseEmailField
            email_lower = email.lower()

            # Check if user exists
            if not self.user_exists(email_lower):
                print(f"Superuser with email '{email_lower}' does not exist.")
                return False

            if not force:
                answer = input(f"Are you sure you want to remove superuser '{email_lower}' and all their memberships? [y/N] ")
                if answer.lower() != 'y':
                    print("Aborted.")
                    return False

            # Escape email for shell safety
            escaped_email = email_lower.replace("'", "'\\''")

            # Delete the user with explicit transaction and error handling
            # KATUser uses email as the unique identifier, not username
            delete_cmd = """
from django.contrib.auth import get_user_model
from django.db import transaction
from tools.models import OrganizationMember
User = get_user_model()
email = '{email}'
try:
    with transaction.atomic():
        user = User.objects.filter(email=email).first()
        if not user:
            user = User.objects.filter(email__iexact=email).first()

        if user:
            # Remove organization memberships first (protected FK)
            deleted_members = OrganizationMember.objects.filter(user=user).delete()
            user.delete()
            print('DELETED_SUCCESS')
        else:
            all_users = list(User.objects.values_list('email', flat=True))
            print(f'NO_USER_FOUND: Looking for {{email!r}} but found users: {{all_users}}')
except Exception as e:
    import traceback
    print(f'ERROR: {{e}}')
    print(traceback.format_exc())
""".format(email=escaped_email)

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                delete_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to delete superuser: {result.stderr}")

            # Check the output
            if "ERROR:" in result.stdout:
                error_msg = result.stdout.split("ERROR:")[1].strip()
                raise RuntimeError(f"Deletion error: {error_msg}")

            if "NO_USER_FOUND" in result.stdout:
                # Extract debug information
                debug_info = result.stdout.split("NO_USER_FOUND:")[1].strip() if "NO_USER_FOUND:" in result.stdout else ""
                raise RuntimeError(f"User with email '{email_lower}' not found during deletion. {debug_info}")

            if "DELETED_SUCCESS" not in result.stdout:
                raise RuntimeError("Delete command did not complete successfully")


            print(f"✓ Superuser with email '{email_lower}' has been removed")
            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def change_password(self, email, new_password):
        """
        Change the password of an existing Django superuser.

        Args:
            email: Email address of the superuser
            new_password: New password to set

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()
            print(f"Using container: {container_id}")

            # Normalize email to lowercase to handle custom user models like KATUser
            # that use LowercaseEmailField
            email_lower = email.lower()

            # Check if user exists
            if not self.user_exists(email_lower):
                print(f"Superuser with email '{email_lower}' does not exist.")
                return False

            # Escape special characters in password for shell safety using repr()
            set_password_cmd = """
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.filter(email__iexact={email}).first()
if user:
    user.set_password({password})
    user.save()
    print('Password changed successfully')
else:
    print('User not found')
""".format(email=repr(email_lower), password=repr(new_password))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                set_password_cmd
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to change password: {result.stderr}")

            if "User not found" in result.stdout:
                print(f"Superuser with email '{email_lower}' not found.")
                return False

            print(f"✓ Password changed successfully for superuser '{email_lower}'")
            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def add_ooi_network(self, org_code, name):
        """
        Add a Network OOI object to an organization via OctoPoes.

        Args:
            org_code: Organization code
            name: Network name (e.g. 'internet')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            cmd_str = """
from octopoes.connector.octopoes import OctopoesAPIConnector
from octopoes.models.ooi.network import Network
from octopoes.api.models import Declaration
from datetime import datetime, timezone

connector = OctopoesAPIConnector('http://octopoesapi:80', {org_code})
network = Network(name={name})
declaration = Declaration(ooi=network, valid_time=datetime.now(timezone.utc))
connector.save_declaration(declaration)
print(f'CREATED: {{network.reference}}')
""".format(org_code=repr(org_code), name=repr(name))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to add network: {result.stderr}")

            if "CREATED:" in result.stdout:
                ref = result.stdout.strip().split("CREATED: ", 1)[1]
                print(f"✓ Network created: {ref}")
                return True

            raise RuntimeError(f"Unexpected output: {result.stdout}")

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def add_ooi_hostname(self, org_code, name, network="internet"):
        """
        Add a Hostname OOI object to an organization via OctoPoes.

        Args:
            org_code: Organization code
            name: Hostname (e.g. 'example.com')
            network: Network name (default: 'internet')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            cmd_str = """
from octopoes.connector.octopoes import OctopoesAPIConnector
from octopoes.models.ooi.dns.zone import Hostname
from octopoes.models.ooi.network import Network
from octopoes.api.models import Declaration
from datetime import datetime, timezone

connector = OctopoesAPIConnector('http://octopoesapi:80', {org_code})
network_ref = Network(name={network}).reference
hostname = Hostname(network=network_ref, name={name})
declaration = Declaration(ooi=hostname, valid_time=datetime.now(timezone.utc))
connector.save_declaration(declaration)
print(f'CREATED: {{hostname.reference}}')
""".format(org_code=repr(org_code), name=repr(name), network=repr(network))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to add hostname: {result.stderr}")

            if "CREATED:" in result.stdout:
                ref = result.stdout.strip().split("CREATED: ", 1)[1]
                print(f"✓ Hostname created: {ref}")
                return True

            raise RuntimeError(f"Unexpected output: {result.stdout}")

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def add_ooi_ip(self, org_code, address, network="internet"):
        """
        Add an IPAddress OOI object to an organization via OctoPoes.
        Auto-detects IPv4 vs IPv6.

        Args:
            org_code: Organization code
            address: IP address string
            network: Network name (default: 'internet')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            cmd_str = """
from octopoes.connector.octopoes import OctopoesAPIConnector
from octopoes.models.ooi.network import Network, IPAddressV4, IPAddressV6
from octopoes.api.models import Declaration
from datetime import datetime, timezone
import ipaddress

connector = OctopoesAPIConnector('http://octopoesapi:80', {org_code})
network_ref = Network(name={network}).reference
addr = ipaddress.ip_address({address})
if isinstance(addr, ipaddress.IPv4Address):
    ip_ooi = IPAddressV4(address=addr, network=network_ref)
else:
    ip_ooi = IPAddressV6(address=addr, network=network_ref)
declaration = Declaration(ooi=ip_ooi, valid_time=datetime.now(timezone.utc))
connector.save_declaration(declaration)
print(f'CREATED: {{ip_ooi.reference}}')
""".format(org_code=repr(org_code), address=repr(address), network=repr(network))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to add IP address: {result.stderr}")

            if "CREATED:" in result.stdout:
                ref = result.stdout.strip().split("CREATED: ", 1)[1]
                print(f"✓ IP address created: {ref}")
                return True

            raise RuntimeError(f"Unexpected output: {result.stdout}")

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def list_ooi_objects(self, org_code, object_type=None):
        """
        List OOI objects in an organization via OctoPoes.

        Args:
            org_code: Organization code
            object_type: Optional filter ('Hostname', 'Network', 'IPAddressV4', 'IPAddressV6')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            cmd_str = """
from octopoes.connector.octopoes import OctopoesAPIConnector
from octopoes.models.ooi.network import Network, IPAddressV4, IPAddressV6
from octopoes.models.ooi.dns.zone import Hostname
from datetime import datetime, timezone

type_map = {{
    'Hostname': Hostname,
    'Network': Network,
    'IPAddressV4': IPAddressV4,
    'IPAddressV6': IPAddressV6,
}}

connector = OctopoesAPIConnector('http://octopoesapi:80', {org_code})
type_filter = {object_type}
if type_filter and type_filter in type_map:
    types = {{type_map[type_filter]}}
else:
    types = set(type_map.values())

result = connector.list_objects(types, valid_time=datetime.now(timezone.utc), limit=500)
if not result.items:
    print('NO_OBJECTS')
else:
    for obj in result.items:
        print(f'OBJ: {{type(obj).__name__}}  {{obj.reference}}')
    print(f'TOTAL: {{result.count}}')
""".format(org_code=repr(org_code), object_type=repr(object_type))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to list objects: {result.stderr}")

            if "NO_OBJECTS" in result.stdout:
                print(f"No objects found in organization '{org_code}'")
                return True

            print(f"Objects in organization '{org_code}':")
            for line in result.stdout.strip().split('\n'):
                if line.startswith("OBJ: "):
                    print(f"  {line[5:]}")
                elif line.startswith("TOTAL: "):
                    print(f"\nTotal: {line[7:]}")

            return True

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def remove_ooi_object(self, org_code, reference, force=False):
        """
        Remove an OOI object from an organization via OctoPoes.

        Args:
            org_code: Organization code
            reference: OOI reference string (e.g. 'Network|internet')
            force: Skip confirmation prompt

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container_id = self.get_container_id()

            if not force:
                answer = input(f"Are you sure you want to remove OOI '{reference}' from organization '{org_code}'? [y/N] ")
                if answer.lower() != 'y':
                    print("Aborted.")
                    return False

            cmd_str = """
from octopoes.connector.octopoes import OctopoesAPIConnector
from datetime import datetime, timezone

connector = OctopoesAPIConnector('http://octopoesapi:80', {org_code})
reference = {reference}
connector.delete(reference, valid_time=datetime.now(timezone.utc))
print(f'DELETED: {{reference}}')
""".format(org_code=repr(org_code), reference=repr(reference))

            cmd = [
                "docker", "exec",
                container_id,
                "python", self.manage_py_path,
                "shell", "-c",
                cmd_str
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to remove object: {result.stderr}")

            if "DELETED:" in result.stdout:
                print(f"✓ Object removed: {reference}")
                return True

            raise RuntimeError(f"Unexpected output: {result.stdout}")

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False


BASH_COMPLETION = r'''_manage_openkat() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    commands="create list-users remove change-password create-organization remove-organization list-organizations add-network add-hostname add-ip list-objects remove-object install-completion"

    # Complete --org at top level
    if [[ "${cur}" == -* && ${COMP_CWORD} -le 2 ]]; then
        COMPREPLY=($(compgen -W "--org --compose-file --service-name --manage-py" -- "${cur}"))
        return 0
    fi

    # Find the subcommand (skip --org and its value)
    local subcmd=""
    local i=1
    while [[ $i -lt ${COMP_CWORD} ]]; do
        case "${COMP_WORDS[$i]}" in
            --org|--compose-file|--service-name|--manage-py)
                ((i+=2))
                ;;
            -*)
                ((i++))
                ;;
            *)
                subcmd="${COMP_WORDS[$i]}"
                break
                ;;
        esac
    done

    # Complete subcommand if not found yet
    if [[ -z "${subcmd}" ]]; then
        COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
        return 0
    fi

    case "${subcmd}" in
        create)
            COMPREPLY=($(compgen -W "--email --password --full-name --only-if-no-superuser-present" -- "${cur}"))
            ;;
        remove)
            COMPREPLY=($(compgen -W "--email --force" -- "${cur}"))
            ;;
        change-password)
            COMPREPLY=($(compgen -W "--email --password" -- "${cur}"))
            ;;
        create-organization)
            COMPREPLY=($(compgen -W "--name --code" -- "${cur}"))
            ;;
        remove-organization)
            COMPREPLY=($(compgen -W "--code --force" -- "${cur}"))
            ;;
        add-network)
            COMPREPLY=($(compgen -W "--org --name" -- "${cur}"))
            ;;
        add-hostname)
            COMPREPLY=($(compgen -W "--org --name --network" -- "${cur}"))
            ;;
        add-ip)
            COMPREPLY=($(compgen -W "--org --address --network" -- "${cur}"))
            ;;
        list-objects)
            COMPREPLY=($(compgen -W "--org --type" -- "${cur}"))
            ;;
        remove-object)
            COMPREPLY=($(compgen -W "--org --reference --force" -- "${cur}"))
            ;;
    esac

    return 0
}

complete -F _manage_openkat manage_openkat
'''


def install_completion():
    """Install bash completion to /etc/bash_completion.d/ and ensure it loads."""
    dest = Path("/etc/bash_completion.d/manage_openkat")
    try:
        dest.write_text(BASH_COMPLETION)
        print(f"✓ Bash completion installed to {dest}")
    except PermissionError:
        print("Error: Permission denied. Run with sudo.", file=sys.stderr)
        sys.exit(1)

    # Ensure bash-completion is enabled in the current user's .bashrc
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        content = bashrc.read_text()
        # Check if bash_completion sourcing is commented out (default on Ubuntu)
        if "#if [ -f /etc/bash_completion ]" in content and "! shopt -oq posix" in content:
            content = content.replace(
                "#if [ -f /etc/bash_completion ] && ! shopt -oq posix; then\n"
                "#    . /etc/bash_completion\n"
                "#fi",
                "if [ -f /etc/bash_completion ] && ! shopt -oq posix; then\n"
                "    . /etc/bash_completion\n"
                "fi",
            )
            bashrc.write_text(content)
            print("✓ Enabled bash-completion in ~/.bashrc (was commented out)")

    print("  Start a new shell session to activate, or run:")
    print(f"  source {dest}")


def main():
    """Main entry point for the script."""

    def strip_quotes(s):
        """Remove surrounding quotes from a string if present."""
        if s is None:
            return s
        # Remove surrounding single or double quotes
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            return s[1:-1]
        return s

    parser = argparse.ArgumentParser(
        description="Manage OpenKAT superusers, organizations, and OOI objects"
    )

    parser.add_argument(
        "--compose-file",
        default="/srv/rocky/docker-compose.yml",
        help="Path to docker-compose.yml file (default: /srv/rocky/docker-compose.yml)"
    )

    parser.add_argument(
        "--service-name",
        default="rocky",
        help="Name of the service in docker-compose (default: rocky)"
    )

    parser.add_argument(
        "--manage-py",
        default="/app/rocky/manage.py",
        help="Path to manage.py inside the container (default: /app/rocky/manage.py)"
    )

    parser.add_argument(
        "--org",
        help="Organization code (required for OOI commands)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new superuser")
    create_parser.add_argument("--email", required=True, help="Email address for the superuser")
    create_parser.add_argument("--password", required=True, help="Password for the superuser")
    create_parser.add_argument("--full-name", help="Full name (first and last name)")
    create_parser.add_argument(
        "--only-if-no-superuser-present",
        action="store_true",
        help="Only create if no superuser accounts currently exist"
    )

    # List users command
    list_parser = subparsers.add_parser("list-users", help="List all users (superusers first)")

    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a superuser")
    remove_parser.add_argument("--email", required=True, help="Email address of the superuser to remove")
    remove_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    # Change password command
    change_pwd_parser = subparsers.add_parser("change-password", help="Change password of a superuser")
    change_pwd_parser.add_argument("--email", required=True, help="Email address of the superuser")
    change_pwd_parser.add_argument("--password", required=True, help="New password for the superuser")

    # Create organization command
    create_org_parser = subparsers.add_parser("create-organization", help="Create a new organization")
    create_org_parser.add_argument("--name", required=True, help="Display name for the organization")
    create_org_parser.add_argument("--code", required=True, help="Short unique code (lowercase slug)")

    # Remove organization command
    remove_org_parser = subparsers.add_parser("remove-organization", help="Remove an organization")
    remove_org_parser.add_argument("--code", required=True, help="Organization code to remove")
    remove_org_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    # List organizations command
    subparsers.add_parser("list-organizations", help="List all organizations")

    # OOI object commands
    add_network_parser = subparsers.add_parser("add-network", help="Add a Network OOI object")
    add_network_parser.add_argument("--org", default=argparse.SUPPRESS, help="Organization code")
    add_network_parser.add_argument("--name", required=True, help="Network name (e.g. 'internet')")

    add_hostname_parser = subparsers.add_parser("add-hostname", help="Add a Hostname OOI object")
    add_hostname_parser.add_argument("--org", default=argparse.SUPPRESS, help="Organization code")
    add_hostname_parser.add_argument("--name", required=True, help="Hostname (e.g. 'example.com')")
    add_hostname_parser.add_argument("--network", default="internet", help="Network name (default: internet)")

    add_ip_parser = subparsers.add_parser("add-ip", help="Add an IP address OOI object")
    add_ip_parser.add_argument("--org", default=argparse.SUPPRESS, help="Organization code")
    add_ip_parser.add_argument("--address", required=True, help="IP address (IPv4 or IPv6)")
    add_ip_parser.add_argument("--network", default="internet", help="Network name (default: internet)")

    list_objects_parser = subparsers.add_parser("list-objects", help="List OOI objects in an organization")
    list_objects_parser.add_argument("--org", default=argparse.SUPPRESS, help="Organization code")
    list_objects_parser.add_argument("--type", dest="object_type", choices=["Hostname", "Network", "IPAddressV4", "IPAddressV6"], help="Filter by object type")

    remove_object_parser = subparsers.add_parser("remove-object", help="Remove an OOI object")
    remove_object_parser.add_argument("--org", default=argparse.SUPPRESS, help="Organization code")
    remove_object_parser.add_argument("--reference", required=True, help="OOI reference (e.g. 'Network|internet')")
    remove_object_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    # Install completion command
    subparsers.add_parser("install-completion", help="Install bash tab completion")

    args = parser.parse_args()

    # Strip quotes from arguments (handles cases where users pass --password 'password')
    if hasattr(args, 'email') and args.email:
        args.email = strip_quotes(args.email)
    if hasattr(args, 'password') and args.password:
        args.password = strip_quotes(args.password)
    if hasattr(args, 'full_name') and args.full_name:
        args.full_name = strip_quotes(args.full_name)
    if hasattr(args, 'name') and args.name:
        args.name = strip_quotes(args.name)
    if hasattr(args, 'code') and args.code:
        args.code = strip_quotes(args.code)
    if hasattr(args, 'org') and args.org:
        args.org = strip_quotes(args.org)
    if hasattr(args, 'address') and args.address:
        args.address = strip_quotes(args.address)
    if hasattr(args, 'network') and args.network:
        args.network = strip_quotes(args.network)
    if hasattr(args, 'reference') and args.reference:
        args.reference = strip_quotes(args.reference)

    # Handle install-completion before validating compose file
    if args.command == "install-completion":
        install_completion()
        sys.exit(0)

    # Validate --org is set for OOI commands
    ooi_commands = {"add-network", "add-hostname", "add-ip", "list-objects", "remove-object"}
    if args.command in ooi_commands and not getattr(args, 'org', None):
        print(f"Error: --org is required for '{args.command}'", file=sys.stderr)
        sys.exit(1)

    # Validate compose file exists
    if not Path(args.compose_file).exists():
        print(f"Error: Docker compose file not found at {args.compose_file}", file=sys.stderr)
        sys.exit(1)

    manager = DjangoSuperuserManager(
        args.compose_file,
        args.service_name,
        args.manage_py
    )

    if args.command == "create":
        success = manager.create_superuser(
            args.email,
            args.password,
            args.full_name,
            args.only_if_no_superuser_present
        )
        sys.exit(0 if success else 1)

    elif args.command == "list-users":
        success = manager.list_users()
        sys.exit(0 if success else 1)

    elif args.command == "remove":
        success = manager.remove_superuser(args.email, args.force)
        sys.exit(0 if success else 1)

    elif args.command == "change-password":
        success = manager.change_password(args.email, args.password)
        sys.exit(0 if success else 1)

    elif args.command == "create-organization":
        success = manager.create_organization(args.name, args.code)
        sys.exit(0 if success else 1)

    elif args.command == "remove-organization":
        success = manager.remove_organization(args.code, args.force)
        sys.exit(0 if success else 1)

    elif args.command == "list-organizations":
        success = manager.list_organizations()
        sys.exit(0 if success else 1)

    elif args.command == "add-network":
        success = manager.add_ooi_network(args.org, args.name)
        sys.exit(0 if success else 1)

    elif args.command == "add-hostname":
        success = manager.add_ooi_hostname(args.org, args.name, args.network)
        sys.exit(0 if success else 1)

    elif args.command == "add-ip":
        success = manager.add_ooi_ip(args.org, args.address, args.network)
        sys.exit(0 if success else 1)

    elif args.command == "list-objects":
        success = manager.list_ooi_objects(args.org, args.object_type)
        sys.exit(0 if success else 1)

    elif args.command == "remove-object":
        success = manager.remove_ooi_object(args.org, args.reference, args.force)
        sys.exit(0 if success else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

