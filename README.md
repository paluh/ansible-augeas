# ansible-augeas

Augeas module which exposes simple API for `match`, `set`, `rm` and `ins` operations. Additionally it allows lens loading through `transform` operation. You can execute commands one by one or in chunk (some of them are probably sensible only in bulk mode e.g. `ins` and `transform`).

## Requirements

- augeas
- augeas python bindings

For example, you can include below playbook before calling ansible augeas plugin
```
- easy_install: name=pip state=latest
- pip: name=python-augeas
```

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


Another complex modification which uses `json_query` to parse results:

    - name: Get dns list
      action: augeas command='match' path="/files/etc/resolv.conf/*"
      register: dns_list

    - name: Add google and opendns servers to resolv.conf
      action: augeas commands="ins nameserver before /files/etc/resolv.conf/nameserver[1]
                               set /files/etc/resolv.conf/nameserver[1] '{{ item }}'"
      when: item not in dns_list|json_query('result[*].value')
      with_items:
        - "8.8.8.8"
        - "208.67.222.222"


Insert example

    - name: Turn on ssh agent forwarding
      action: augeas commands='ins ForwardAgent before "/files/etc/ssh/sshd_config"
                               set "/files/etc/ssh/sshd_config/ForwardAgent" "yes"'


__It's better to use quotation all the time when defining values__. If you remove quotation (if you change `'no'` to `no` and `'yes'` to `yes`) from values declartions in below snippet they are going to be parsed as boolean values (`yes` and `no` are correct boolean values in yaml). As augeas is missing validation in case of this lens you are going to end up with unusable ssh configuration (with `RSAAuthentication True` etc.) and you won't be able to login again to your host ;-).

    - name: Improve ssh server security
      action: augeas command="set" path="/files/etc/ssh/sshd_config/{{ item.path }}" value="{{ item.value }}"
      with_items:
        - path: 'PermitRootLogin'
          value: 'no'
        - path: 'PasswordAuthentication'
          value: 'no'
        - path: 'UsePAM'
          value: 'no'
        - path: 'ChallengeResponseAuthentication'
          value: 'no'
        - path: 'X11Forwarding'
          value: 'no'
        - path: 'RSAAuthentication'
          value: 'yes'
        - path: 'PubkeyAuthentication'
          value: 'yes'
      notify:
        - Restart sshd

 Of course above snippet could be rewritten in more efficient manner with bulk execution (usage of `commands`) - check next sections examples.

### Bulk command execution

The `commands` option allow to supply augeas command sequences:

    - name: Improve ssh server security
      augeas: commands="set /files/etc/ssh/sshd_config/PermitRootLogin no
                        set /files/etc/ssh/sshd_config/PasswordAuthentication no
                        set /files/etc/ssh/sshd_config/UsePAM no
                        set /files/etc/ssh/sshd_config/ChallengeResponseAuthentication no
                        set /files/etc/ssh/sshd_config/X11Forwarding no
                        set /files/etc/ssh/sshd_config/RSAAuthentication yes
                        set /files/etc/ssh/sshd_config/PubkeyAuthentication yes"
      notify:
        - Restart sshd

And another example:

    - name: Add piggy to /etc/hosts
      action:  augeas commands='set /files/etc/hosts/01/ipaddr 192.168.0.1
                                set /files/etc/hosts/01/canonical pigiron.example.com
                                set /files/etc/hosts/01/alias[1] pigiron
                                set /files/etc/hosts/01/alias[2] piggy'

Example of correct quoting in commands expressions (augeas requires quotes in path matching expressions: iface[.=\"eth0\"]):

    - name: Redefine eth0 interface
      action: augeas commands='rm /files/etc/network/interfaces/iface[.=\"eth0\"]
                               set /files/etc/network/interfaces/iface[last()+1] eth0
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/family inet
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/method manual
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/pre-up "ifconfig $IFACE up"
                               set /files/etc/network/interfaces/iface[.=\"eth0\"]/pre-down "ifconfig $IFACE down"'

### Managing non-standard files and optimizing execution

To manage files not automatically detected by augeas, we can use `lens & file
options`, which are used by the module for an implicit `transform` command which
makes the file available in simple `command` actions. When file is defined,
the path given to ansible is relative to the file itself, as the module takes
care of building the proper augeas path.

Using them, the example about sshd_config in a custom location can be written as

    - name: Fetch sshd allowed users in custom location
      action: augeas commands="match" lens="sshd" file="/home/paluh/programming/ansible/tests/sshd_config" path="AllowUsers/*"
      register: ssh_allowed_users

When `file` and `lens` options are in use, this module prevents augeas from loading
 all other lenses (it initializes augeas with `NO_MODL_AUTOLOAD` flag). This can
 significantly speedup execution of your action. In other words - __you can also use `file`
 and `lens` options, when you work on standard files, to make this processing faster__.

#### Transform example

**NOTE : ** Although this transform examples are kept, its usually better to use `lens & file` action, which is more efficient and takes care of files reloading etc. Some scenarios require usage of `transform` tough.

You should be careful when using `transform` and __remember to load files after transformations__. You have to be also aware that `load` command will __"remove everything underneath
`/augeas/files` and `/files`, regardless of whether any entries have been modified or not"__ (http://augeas.net/docs/references/c_api/files/augeas-h.html#aug_load) and that `load` is costly operation. So it you sould order your commands and put all `transforms` on the beginning, then use `load` and then other transformations.

    - name: Modify sshd_config in custom location
      action: augeas commands='transform "sshd" "incl" "/home/paluh/programming/ansible/tests/sshd_config"
                               load
                               match "/files/home/paluh/programming/ansible/tests/sshd_config/AllowUsers/*"'

## Debugging

If you want to check files which are accessible by augeas on server just run:

    ansible all -u USERNAME -i INVENTORY_FILE -m augeas -a \'command="match" path="/augeas/files//*"

In case of any errors during augeas execution of your operations this module will return content of `/augeas//error` and you should be able to find problems related to your actions


## Conributing

Please send me pull requests with additional examples of complex editing scenarios. I'm going to put them here.

