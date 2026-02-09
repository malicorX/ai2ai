import urllib.request
import sys
url = sys.argv[1] if len(sys.argv) > 1 else "http://host.docker.internal:11892/"
try:
    r = urllib.request.urlopen(url, timeout=5)
    print("OK", r.getcode())
except Exception as e:
    print("ERR", type(e).__name__, str(e))
    sys.exit(1)
