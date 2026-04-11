#!/usr/bin/python3
# -*- coding: utf-8 -*-
DOCUMENTATION = r'''
---
module: persist_password
short_description: Ensure a persistent password stored as VARIABLE=password in a file
description:
  - Generate or reuse a password stored in an environment-style file on the remote host.
  - If the requested variable is missing or empty the module will generate a secure password,
    add or update the line "VARIABLE=password" and optionally set owner, group and permissions.
version_added: "1.0"
options:
  path:
    description:
      - Full path to the env-style file to create or update.
    required: true
    type: path
  variable:
    description:
      - Environment variable name to store the password under (no whitespace or '=').
    required: true
    type: str
  factname:
    description:
        - Name of the Ansible fact to set with the password value.
    required: false
    type: str
    default: null
  length:
    description:
      - Password length to generate when creating a new password.
    required: false
    type: int
    default: 32
  chars:
    description:
      - Comma-separated charset tokens. Supported: ascii_letters, letters, digits, punctuation, hex.
    required: false
    type: str
    default: ascii_letters,digits
  owner:
    description:
      - UID or username to set as file owner.
    required: false
    type: str
    default: root
  group:
    description:
      - GID or group name to set as file group.
    required: false
    type: str
    default: root
  mode:
    description:
      - File mode as an octal string (e.g. "0600") or integer-compatible string.
    required: false
    type: str
    default: "0600"
  rotatedays:
    description:
      - Change the password if older than this many days. 0 means never rotate.
    required: false
    type: int
    default: 0

'''

EXAMPLES = r'''
- name: Persist application password
  persist_password:
    path: /etc/myapp/creds.env
    variable: MYAPP_PASSWORD
    factname: myapp_password
    owner: root
    group: root
    mode: "0600"
    length: 40
    chars: ascii_letters,digits,punctuation
    rotatedays: 30
'''

RETURN = r'''
changed:
  description: whether the module made changes
  type: bool
path:
  description: the file path processed
  type: str
variable:
  description: the variable name used
  type: str
password_length:
  description: length of returned password
  type: int
ansible_facts:
  description: mapping with the factname or variable and password
  type: dict
password:
    description: the password value
    type: str
'''

from ansible.module_utils.basic import AnsibleModule
import os
import tempfile
import secrets
import string
import time
import pwd
import grp

def build_charset(spec):
    available = {
        'ascii_letters': string.ascii_letters,
        'letters': string.ascii_letters,
        'digits': string.digits,
        'punctuation': string.punctuation,
        'hex': string.hexdigits.lower(),
    }
    if spec is None:
        raise ValueError("chars parameter is required")
    tokens = [t.strip() for t in str(spec).split(',') if t.strip()]
    chars_parts = []
    invalid = []
    for t in tokens:
        if t in available:
            chars_parts.append(available[t])
        else:
            invalid.append(t)
    if invalid:
        raise ValueError("Invalid chars tokens: %s" % ", ".join(invalid))
    if not chars_parts:
        raise ValueError("No valid characters resolved from chars parameter.")
    return ''.join(chars_parts)

def resolve_uid_gid(owner, group):
    uid = -1
    gid = -1
    if owner is not None:
        try:
            uid = int(owner)
        except Exception:
            try:
                uid = pwd.getpwnam(owner).pw_uid
            except KeyError:
                raise ValueError("Invalid owner: %s" % owner)
            except Exception as e:
                raise ValueError("Failed resolving owner '%s': %s" % (owner, e))
    if group is not None:
        try:
            gid = int(group)
        except Exception:
            try:
                gid = grp.getgrnam(group).gr_gid
            except KeyError:
                raise ValueError("Invalid group: %s" % group)
            except Exception as e:
                raise ValueError("Failed resolving group '%s': %s" % (group, e))
    return uid, gid

def validate_variable(name):
    if not name or '=' in name or any(c.isspace() for c in name):
        raise ValueError("`variable` must be non-empty and must not contain whitespace or '='")
    return name

def generate_password(length, chars):
    try:
        length = int(length)
    except Exception:
        raise ValueError("Invalid length: %s" % length)
    if length <= 0:
        raise ValueError("length must be a positive integer")
    return ''.join(secrets.choice(chars) for _ in range(length))

def read_env_lines(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().splitlines()
    except Exception as e:
        raise IOError("Failed reading file %s: %s" % (path, e))

def write_atomic(path, lines, mode_int, uid, gid):
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
    except Exception as e:
        raise IOError("Failed to create directories for %s: %s" % (path, e))

    data = "\n".join(lines)
    if not data.endswith("\n"):
        data += "\n"

    tmp = None
    try:
        # Create temp file in same directory to allow atomic replace on same filesystem
        fd, tmp = tempfile.mkstemp(prefix='.persist_password.', dir=parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as tf:
                tf.write(data)
                tf.flush()
                os.fsync(tf.fileno())
        except Exception as e:
            # ensure file descriptor closed
            raise IOError("Failed writing temp file for %s: %s" % (path, e))

        # Apply permissions to temp file first
        try:
            os.chmod(tmp, mode_int)
        except Exception:
            # continue; final chmod will be attempted after replace
            pass

        os.replace(tmp, path)
        tmp = None  # moved successfully; don't try to unlink

        # Attempt chown; if not permitted, raise only for unexpected errors
        try:
            if uid != -1 or gid != -1:
                os.chown(path, uid if uid != -1 else -1, gid if gid != -1 else -1)
        except PermissionError:
            # ignore permission errors when not root
            pass
        except Exception as e:
            raise IOError("Failed to set owner/group on %s: %s" % (path, e))

        try:
            os.chmod(path, mode_int)
        except Exception as e:
            raise IOError("Failed to set mode on %s: %s" % (path, e))
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

def run_module():
    module_args = dict(
        path=dict(type='path', required=True),
        variable=dict(type='str', required=True),
        fact_name=dict(type='str', required=False, default=None),
        length=dict(type='int', default=32),
        chars=dict(type='str', default='ascii_letters,digits'),
        owner=dict(type='str', required=False, default='root'),
        group=dict(type='str', required=False, default='root'),
        mode=dict(type='str', required=False, default='0600'),
        rotatedays=dict(type='int', required=False, default=0),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    path = module.params['path']
    variable = module.params['variable']
    fact_name = module.params['fact_name']
    length = module.params['length']
    chars_spec = module.params['chars']
    owner = module.params['owner']
    group = module.params['group']
    mode_str = module.params['mode']
    rotatedays = module.params['rotatedays']

    try:
        variable = validate_variable(variable)
    except ValueError as e:
        module.fail_json(msg=str(e))

    # Parse mode as octal
    try:
        mode_int = int(str(mode_str), 8)
    except Exception:
        module.fail_json(msg="Invalid mode '%s'. Provide an octal string like '0600'." % mode_str)

    # Resolve owner/group
    try:
        uid, gid = resolve_uid_gid(owner, group)
    except ValueError as e:
        module.fail_json(msg=str(e))

    # Build charset
    try:
        chars = build_charset(chars_spec)
    except ValueError as e:
        module.fail_json(msg=str(e))

    file_exists = os.path.exists(path)
    lines = []
    existing_value = None
    rotepassword = False

    if file_exists:
        file_mtime = os.path.getmtime(path)
        file_age_days = (time.time() - file_mtime) / (24 * 3600) if rotatedays > 0 else 0
        if rotatedays > 0 and file_age_days >= rotatedays:
            # Force regeneration by treating as if variable is missing
            rotepassword = True
        try:
            lines = read_env_lines(path)
        except Exception as e:
            module.fail_json(msg=str(e))
        for idx, raw in enumerate(lines):
            stripped = raw.strip()
            if not stripped or stripped.lstrip().startswith('#'):
                continue
            if stripped.startswith(variable + "="):
                # split only on first '=' to allow '=' in the value
                _, val = stripped.split('=', 1)
                existing_value = val
                break

    changed = False
    password = None

    if existing_value is not None and existing_value != "" and not rotepassword:
        password = existing_value
    else:
        try:
            password = generate_password(length, chars)
        except ValueError as e:
            module.fail_json(msg=str(e))
        new_line = "%s=%s" % (variable, password)
        if file_exists:
            updated = False
            for idx, raw in enumerate(lines):
                stripped = raw.strip()
                if not stripped or stripped.lstrip().startswith('#'):
                    continue
                if stripped.startswith(variable + "="):
                    lines[idx] = new_line
                    updated = True
                    break
            if not updated:
                lines.append(new_line)
        else:
            lines = [new_line]
        changed = True

    # Perform write if needed
    if changed and not module.check_mode:
        try:
            write_atomic(path, lines, mode_int, uid, gid)
        except Exception as e:
            module.fail_json(msg=str(e))

    # Prepare result
    if fact_name:
        fact_name_used = fact_name
    else:
        fact_name_used = variable
    result = dict(
        changed=changed,
        path=path,
        variable=variable,
        password_length=len(password) if password else 0,
        ansible_facts={fact_name_used: password},
        password=password,
    )
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()