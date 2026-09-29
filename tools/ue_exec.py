# Run a Python snippet/file inside the running Stalker2 Mod Editor via UE remote execution.
import sys, time
sys.path.insert(0, r"G:/Epic Games/STALKER2ZoneKit/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python")
import remote_execution as re_

def main():
    src = sys.argv[1]
    code = open(src, encoding="utf-8").read() if src.endswith(".py") else src
    r = re_.RemoteExecution()
    r.start()
    deadline = time.time() + 5.0
    while time.time() < deadline and not r.remote_nodes:
        time.sleep(0.1)
    if not r.remote_nodes:
        print("NO_EDITOR_NODE (remote execution not enabled in editor)"); r.stop(); sys.exit(2)
    r.open_command_connection(r.remote_nodes[0]["node_id"])
    res = r.run_command(code, exec_mode=re_.MODE_EXEC_FILE, raise_on_failure=False)
    for o in res.get("output", []):
        print(f"[{o['type']}] {o['output']}")
    if not res.get("success", False):
        print("FAILED:", res.get("result")); 
    r.stop()
main()
