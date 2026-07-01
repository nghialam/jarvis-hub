
import sys, traceback  
sys.path.insert(0, str(__import__('pathlib').Path('.').absolute()))
try:
    import flask as f
    print("Flask import OK:", f.__version__)
except Exception as e:
    print("Flask import FAILED:", e)

try:
    os = __import__('os')
    app_path = os.path.join(os.getcwd(), 'app.py')
    code_source = open(app_path).read()
    compile(code_source, 'app.py', 'exec')
    print("Compilation OK")
except Exception as e:
    print("Compile FAILED:", e)
    
# Now try the actual import with a timeout-like approach  
import threading, signal

def interrupt():
    raise TimeoutError("Import took too long")

timer = threading.Timer(8.0, interrupt)
try:
    timer.start()
    import app as test_app
    timer.cancel()
    print("App import OK!")
    # Check if server started  
    try:
        r = __import__('urllib.request').request.urlopen('http://localhost:8100/api/health')
        print("Health:", r.read().decode()[:200])
    except Exception as he:
        print("Server not ready:", he)
except TimeoutError as te:
    timer.cancel()
    print("IMPORT TIMEOUT - app.py likely has a blocking call")
except ImportError as ie:
    print("ImportError (non-blocking):", ie)
except Exception as e2:
    traceback.print_exc()
