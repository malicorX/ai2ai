import os
import subprocess

os.environ["PATH"] = "/home/malicor/.nvm/versions/node/v22.22.0/bin:" + os.environ.get("PATH", "")
os.environ["OPENCLAW_GATEWAY_URL"] = "ws://127.0.0.1:18789"
os.environ["OPENCLAW_GATEWAY_TOKEN"] = "5d670845a55742a4137a0ab996966718e22cf71449e4fc1d"

fn = (
    "() => {"
    "const titles = [];"
    "document.querySelectorAll('a').forEach(a => {"
    "  const t = (a.textContent || '').trim();"
    "  if (t && t.length > 15 && t.length < 120) titles.push(t);"
    "});"
    "const unique = [];"
    "for (const t of titles) { if (!unique.includes(t)) unique.push(t); }"
    "return { title: document.title, titles: unique.slice(0, 30) };"
    "}"
)

subprocess.run(
    [
        "openclaw",
        "browser",
        "evaluate",
        "--browser-profile",
        "openclaw",
        "--fn",
        fn,
        "--json",
    ],
    check=False,
)
