# termux-nas

Private, rootless SMB browsing experiment for Termux.

## Current status

The current CLI opens a **virtual NAS shell**. Within `nas shell`, `cd ~/nas`, `ls`, `pwd`, `cat`, `get`, and `put` operate on an SMB share. This is not an Android mount: `~/nas` is not a NAS-backed path in the ordinary Termux shell, and arbitrary tools such as `find` and `nano` do not yet operate on it. The longer-term goal is to investigate a rootless per-process filesystem bridge for that behavior; see [architecture](docs/architecture.md).

No NAS connection has been tested on an Android device yet. The initial automated tests cover path handling and shell navigation with a fake backend.

## Install privately on your phone

Copy or clone this repository into **Termux home**. Then run in Termux:

```sh
pkg install python python-cryptography
cd ~/termux-nas
python -m pip install .
nas --help
```

You do not need to publish the repository or a package. To update a local installation after changing the source, run `python -m pip install .` again. If installation fails while building the `cryptography` dependency, ensure `python-cryptography` is installed from the Termux package repository first.

## Connect

```sh
nas add home --host 192.168.1.10 --share Shared --user your_username
nas shell home
```

The password is requested when the shell starts. Connection details are stored in `~/.config/termux-nas/connections.json`; passwords are not stored.

Inside `nas shell`:

```text
~/nas $ ls
~/nas $ cd Photos
~/nas/Photos $ cat notes.txt
~/nas/Photos $ get picture.jpg
~/nas/Photos $ put ~/local-file.txt
~/nas/Photos $ exit
```

`get` downloads to the current **local** Termux directory by default. `put` uploads from a local Termux path. Both refuse to overwrite an existing destination. Quote paths containing spaces.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The SMB adapter uses the [smbprotocol high-level `smbclient` API](https://github.com/jborean93/smbprotocol). The CLI is kept separate from that adapter so navigation can be tested without a NAS.
