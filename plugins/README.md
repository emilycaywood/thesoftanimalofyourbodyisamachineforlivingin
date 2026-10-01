# Your plugins

Every `*.py` file in this folder is loaded by CALFLAB at start-up and reloaded
when it changes (files starting with `_` are ignored).

```powershell
.\calflab.ps1 new-plugin fitness_term quiet_feet   # template + contract test
.\calflab.ps1 plugins                              # list what is registered
```

Plugin types: `gene_definition`, `part_generator`, `joint_type`, `component`,
`controller`, `behavior`, `fitness_term`, `behavior_descriptor`, `optimizer`,
`simulator`, `compute_backend`, `exporter`, `analysis`, `panel`, `command`.

Declare parameters with `calflab.schema.P(...)`; the web app builds the
property panel, node sockets and tooltips from them. You never write UI code
for a plugin. See `CLAUDE.md` for the rules each type must follow.
