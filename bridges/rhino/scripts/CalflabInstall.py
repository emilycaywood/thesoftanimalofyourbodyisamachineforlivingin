#! python3
"""CalflabInstall: register the Calflab* commands as Rhino aliases (run once).

After this, type CalflabConnect, CalflabPull, CalflabPush or CalflabLiveSync in
the Rhino command line like any other command.
"""
import os

import rhinoscriptsyntax as rs

HERE = os.path.dirname(os.path.abspath(__file__))
COMMANDS = ["CalflabConnect", "CalflabPull", "CalflabPush", "CalflabLiveSync"]


def main():
    for name in COMMANDS:
        script = os.path.join(HERE, name + ".py")
        macro = '_-ScriptEditor _Run "%s"' % script
        if rs.IsAlias(name):
            rs.SetAliasMacro(name, macro)
        else:
            rs.AddAlias(name, macro)
        print("CALFLAB: alias %s -> %s" % (name, script))
    print("CALFLAB: done. Start the lab (calflab lab), then type CalflabPull.")


main()
