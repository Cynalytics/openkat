_manage_openkat() {
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
