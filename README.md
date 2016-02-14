# ansible-augeas

Augeas module which exposes simple API for `match`, `set`, `rm` and `ins` operations. Additionally it allows lens loading through `transform` operation. You can execute commands one by one or in chunk (some of them are probably sensible only in bulk mode e.g. `ins` and `transform`).

## Requirements

- augeas
- augeas python bindings

## Options

- `command`
    - required: when `commands` is not used
    - choices: [`set`, `ins`, `rm`, `match`, `transform`, `load`]
    - description:
      Whether given path should be modified, inserted (ins command can be really used in multicommand mode), removed or matched.  
      Command "match" passes results through "result" attribute - every item on this list is an object with "label" and "value" (check second example below). Other commands returns true in case of any modification (so this value is always equal to "changed" attribue - this make more sens in case of bulk execution)  
      Every augeas action is a separate augeas session, so `ins` command has probably only sens in bulk mode (when command=`commands`)
- `path`:
    - required: when any `command` is used
    - description: Variable path. With `lens` and `file`, it is the relative path within the file tree (see examples).
- `value`:
    - required: when `command = set`
    - description: Variable value.
- `label`:
    - required: when `command = ins`
    - description: Label for new node.
- `where`:
    - required: false
    - default: 'after'
    - choices: [`before`, `after`]
    - description: Position of node insertion against given `path`.
- `lens`:
    - required: false
    - description: Augeas lens to be loaded.
- `file`:
    - required: false
    - description: File to parse.
- `commands`
    - required: when `command` is not used
    - description: Execute many commands at once (some configuration entries have to be created/updated at once - it is impossible to split them across multiple "set" calls). Standard shell quoting is allowed (rember to escape all quotes inside pahts/values - check last example).  
     Expected formats: "set PATH VALUE", "rm PATH" or "match PATH" (look into examples for more details). You can separate commands with any white characters (new lines, spaces etc.). Result is passed through `result` attribute and contains list of tuples: (command, command result).
- `root`:
    - required: false
    - description: The filesystem root - config files are searched realtively to this path (fallbacks to `AUGEAS_ROOT` which fallbacks to  `/`).
- `loadpath`:
    - required: false
    - description: Colon-spearated list of directories that modules should be searched in.

## Examples

Simple value change

    - name: Force password on sudo group
      action: augeas path=/files/etc/sudoers/spec[user=\"sudo\"]/host_group/command/tag value=PASSWD

Results of `match` command - given below action:

    - name: Fetch sshd allowed users
      action: augeas command="match" path="/files/etc/ssh/sshd_config/AllowUsers/*"
      register: ssh_allowed_users

you can expect value of this shape to be set in `ssh_allowed_users` variable:

    {"changed": false,
     "result": [{"label": "/files/etc/ssh/sshd_config/AllowUsers/1",
                 "value": "paluh"},
                {"label": "/files/etc/ssh/sshd_config/AllowUsers/2",
                 "value": "foo"},
                {"label": "/files/etc/ssh/sshd_config/AllowUsers/3",
                 "value": "bar"}]}

Quite complex modification - fetch values lists and append new value only if it doesn't exists already in config

    - name: Check whether given user is listed in sshd_config
      action: augeas command='match' path="/files/etc/ssh/sshd_config/AllowUsers/*[.=\"{{ user }}\"]"
      register: user_entry
    - name: Allow user to login through ssh
      action: augeas command="set" path="/files/etc/ssh/sshd_config/AllowUsers/01" value="{{ user }}"
      when: "user_entry.result|length == 0"

Insert example

    - name: Turn on ssh agent forwarding
      action: augeas commands='ins ForwardAgent before "/files/etc/ssh/sshd_config"
                               set "/files/etc/ssh/sshd_config/ForwardAgent" "yes"'

### Bulk command execution

The `commands`option allow to supply complex augeas command sequences

    - name: Add piggy to /etc/hosts
      action:  augeas commands='set /files/etc/hosts/01/ipaddr 192.168.0.1
                                set /files/etc/hosts/01/canonical pigiron.example.com
                                set /files/etc/hosts/01/alias[1] pigiron
                                set /files/etc/hosts/01/alias[2] piggy'

**NOTE : ** Although this transform example is kept, its action can be more easily done with lens & file options described below.  
Transform examples - __it is important to load files after transformations__.
You have to be aware that `load` command will "remove everything underneath
`/augeas/files` and `/files`, regardless of whether any entries have been
modified or not" and that `load` is costly operation. You should order your
commands and put `transforms`, then `load` and then other transformations.

    - name: Modify sshd_config in custom location
      action: augeas commands='transform "sshd" "incl" "/home/paluh/programming/ansible/tests/sshd_config"
                               load
                               match "/files/home/paluh/programming/ansible/tests/sshd_config/AllowUsers/*"'

Correct quoting in commands expressions (augeas requires quotes in path matching expressions: iface[.=\"eth0\"])

    - name: Redefine eth0 interface
      action: augeas commands='rm /files/etc/network/interfaces/iface[.=\"eth0\"]
                               set /files/etc/network/interfaces/iface[last()+1] eth0
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/family inet
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/method manual
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/pre-up "ifconfig $IFACE up"
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/pre-down "ifconfig $IFACE down"'

### Managing non-standard files

To manage files not automatically detected by augeas, we can use lens & file
options, which are used by the module for an implicit `transform` command which
makes the file available in simple `command` actions. When file is defined,
the path given to ansible is relative to the file itself, as the module takes
care of building the proper augeas path.

Using them, the example about sshd_config in a custom location can be written as

    - name: Fetch sshd allowed users in custom location
      action: augeas commands="match" lens="sshd" file="/home/paluh/programming/ansible/tests/sshd_config" path="AllowUsers/*"
      register: ssh_allowed_users

## Debugging

If you want to check files which are accessible by augeas on server just run:

    ansible all -u USERNAME -i INVENTORY_FILE -m augeas -a \'command="match" path="/augeas/files//*"

In case of any errors during augeas execution of your operations this module will return content of `/augeas//error` and you should be able to find problems related to your actions
