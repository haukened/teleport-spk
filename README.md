# teleport-spk
A script to build the teleport daemon for Synology NAS devices

## Virtual environments and root privileges

Due to some strangeness with the way Synology has been packing their TAR files, their scripts need to be run with root privileges.  This gets sticky with virtual envs, and required packages.

1. Run `python3 -m venv .venv` to create and activate a new virtual environment.
1. Run `pip install -r requirements.txt` to install the required python packages to the virtual environment
1. Run `deactivate` to leave the venv
1. Run `sudo /path/to/your/.venv/bin/python3 build-spk.py --processor <your processor family>` to execute the script as root, sourcing packages from the virtual environment

## Command line options

| Command | Description | Choices | Default |
| --- | --- | --- | --- |
| `-h` `--help` | Show the help screen | None |
| `--dsm-version` | The supported DSM version | One of: `[6.0, 6.1, 6.2, 6.2.2, 6.2.3, 6.2.4, 7.0, 7.1, 7.2]` | Latest, currently `7.2` |
| `--processor` | The processor family | See [this page](https://www.synology.com/knowledgebase/DSM/tutorial/Compatibility_Peripherals/What_kind_of_CPU_does_my_NAS_have) | None |

## Supported DSM Versions

Supported versions are determined by Synolog and are pulled from github when the script is run. Those are currently:

- 6.0
- 6.1
- 6.2
- 6.2.2
- 6.2.3
- 6.2.4
- 7.0
- 7.1
- 7.2

## Supported processor families

Supported processor families are determined by Synology. Please check [this page](https://www.synology.com/knowledgebase/DSM/tutorial/Compatibility_Peripherals/What_kind_of_CPU_does_my_NAS_have) to determine what processor family your model has.