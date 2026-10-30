import os
import threading
import time
import pytest

def closer(win):
    time.sleep(1)
    win.destroy()

@pytest.mark.skipif(os.environ.get("RUN_WEBVIEW_SMOKE") != "1", reason="Native window smoke test separated from regular automated test suite")
def test_native_window():
    import webview
    window = webview.create_window("Cell Figure Studio", html="<h1 style='font-family:sans-serif'>Native window OK</h1>", width=800, height=500)
    threading.Thread(target=closer, args=(window,), daemon=True).start()
    webview.start(gui="edgechromium")

if __name__ == "__main__":
    os.environ["RUN_WEBVIEW_SMOKE"] = "1"
    test_native_window()
