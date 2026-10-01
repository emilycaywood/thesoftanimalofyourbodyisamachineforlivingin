# CALFLAB user guide

This guide grows with the tool. Sections marked *(planned)* describe
scaffolded features that are not usable yet.

## 1. Install and run

Requirements: Windows 11, Python (any 3.x, used only to bootstrap uv),
Node LTS. Rhino 8 and Blender 4.x are optional.

```powershell
.\calflab.ps1 setup     # creates the Python env, installs web deps, makes the sample project
.\calflab.ps1 doctor    # checks tools, Rhino/Blender paths, ports
.\calflab.ps1 lab       # starts the server and the web app, opens the browser
```

The environment lives in `%LOCALAPPDATA%\calflab` (not in the repo). To remove
it, delete that folder and run `setup` again.

> (Further sections are added as features land.)
