#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serveur web local_ia, basé uniquement sur la bibliothèque standard."""

from __future__ import annotations

import json
import mimetypes
import socket
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
CONFIG_PATH = BASE_DIR / "config.json"
CHAT_DIR = BASE_DIR / "chats"
OLLAMA_DEFAULT = "http://127.0.0.1:11434"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def config():
    data = read_json(CONFIG_PATH, {})
    return data if isinstance(data, dict) else {}


def ollama_url():
    value = config().get("ollama", {})
    if isinstance(value, dict):
        url = value.get("url") or OLLAMA_DEFAULT
    else:
        url = OLLAMA_DEFAULT
    url = str(url).rstrip("/")
    # ia_agent utilise /api/chat ; l'utilisateur peut fournir localhost:11434.
    if url.endswith("/api"):
        url = url[:-4]
    return url


def installed_models():
    """Retourne toujours un dictionnaire de la forme {models, error}."""
    try:
        req = Request(ollama_url() + "/api/tags", method="GET")
        with urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))

        # Ollama renvoie normalement {"models": [...]}. On tolère aussi
        # une réponse directement sous forme de liste pour éviter qu'une
        # réponse atypique fasse planter les endpoints web.
        raw_models = data.get("models", []) if isinstance(data, dict) else data
        if not isinstance(raw_models, list):
            raw_models = []

        models = [
            {
                "name": x.get("name", ""),
                "size": x.get("size", 0),
                "modified_at": x.get("modified_at", ""),
            }
            for x in raw_models
            if isinstance(x, dict) and x.get("name")
        ]
        return {"models": models, "error": None}
    except Exception as exc:
        return {"error": str(exc), "models": []}


def chats():
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for p in CHAT_DIR.glob("*.json"):
        if not p.stem.isdigit():
            continue
        data = read_json(p, {})
        if isinstance(data, dict):
            data.setdefault("id", int(p.stem))
            data.setdefault("messages", [])
            data.setdefault("summary", "")
            data.setdefault("topic", "")
            result.append(data)
    return sorted(result, key=lambda x: int(x.get("id", 0)), reverse=True)


def get_chat(chat_id):
    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return None
    p = CHAT_DIR / f"{cid}.json"
    data = read_json(p, None)
    return data if isinstance(data, dict) else None


def save_chat(chat):
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    chat["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (CHAT_DIR / f"{int(chat['id'])}.json").write_text(
        json.dumps(chat, ensure_ascii=False, indent=4), encoding="utf-8"
    )


def create_chat():
    ids = [int(p.stem) for p in CHAT_DIR.glob("*.json") if p.stem.isdigit()]
    now = datetime.now().isoformat(timespec="seconds")
    chat = {
        "id": max(ids, default=0) + 1,
        "created_at": now,
        "updated_at": now,
        "summary": "",
        "topic": "",
        "messages": [],
    }
    save_chat(chat)
    return chat


def model_from_config():
    c = config()
    # Supporte la structure actuelle et l'ancienne structure {"model": "..."}.
    if isinstance(c.get("ollama"), dict) and c["ollama"].get("model"):
        return str(c["ollama"]["model"])
    return str(c.get("model", ""))


def ask_ollama(model, messages):
    payload = {"model": model, "messages": messages, "stream": False}
    raw = json.dumps(payload).encode("utf-8")
    req = Request(
        ollama_url() + "/api/chat",
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = 120
    try:
        timeout = int(config().get("ollama", {}).get("timeout", 120))
    except Exception:
        pass
    with urlopen(req, timeout=max(5, timeout)) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result.get("message", {}).get("content", "").strip()


def chat_with_model(model, chat):
    history = []
    for msg in chat.get("messages", [])[-20:]:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
    # Le système est volontairement construit simplement ici : la configuration
    # détaillée reste gérée par l'interface CLI et ia_agent.
    system = (
        "Tu es un assistant IA local. Réponds en français sauf si l'utilisateur "
        "demande une autre langue. Sois clair, utile et honnête."
    )
    try:
        import ia_agent
        context = ia_agent.load_context()
        memories = []
        try:
            conn = ia_agent.init_database()
            memories = ia_agent.get_memories(conn)
            conn.close()
        except Exception:
            pass
        system = ia_agent.build_system_prompt(
            memories=memories,
            topic=chat.get("topic"),
            context=context,
            external_info=None,
        )
    except Exception:
        pass
    # Le serveur web utilise directement le moteur local_ia (ia_agent.py).
    # main.py n'intervient donc pas dans les requêtes de chat.
    try:
        import ia_agent
        timeout = 120
        try:
            timeout = int(config().get("ollama", {}).get("timeout", 120))
        except Exception:
            pass
        return ia_agent.ask_ollama(
            [{"role": "system", "content": system}] + history,
            model=model,
            timeout=timeout,
        )
    except Exception:
        # Secours direct vers Ollama si le module local_ia n'est pas importable.
        return ask_ollama(model, [{"role": "system", "content": system}] + history)


def json_out(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "local_ia/2.0"

    def log_message(self, fmt, *args):
        print("[WEB] " + (fmt % args))

    def static(self, relative):
        root = WEB_DIR.resolve()
        target = (WEB_DIR / relative).resolve()
        if root not in target.parents and target != root:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".js":
            content_type = "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("" if "charset" in content_type else "; charset=utf-8"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.static("index.html")
        if path in ("/app.js", "/style.css"):
            return self.static(path[1:])
        if path == "/api/status":
            models = installed_models()
            return json_out(self, {
                "ok": not bool(models.get("error")),
                "ollama": ollama_url(),
                "model": model_from_config(),
                "models": models.get("models", []),
                "error": models.get("error"),
            })
        if path == "/api/models":
            models = installed_models()
            return json_out(self, {
                "installed": models.get("models", []),
                "error": models.get("error"),
            })
        if path == "/api/chats":
            return json_out(self, {"chats": chats()})
        if path.startswith("/api/chats/"):
            return json_out(self, {"chat": get_chat(path.rsplit("/", 1)[-1])})
        if path == "/api/config-info":
            c = config()
            return json_out(self, {
                "model": model_from_config(),
                "ollama_url": ollama_url(),
                "language": c.get("utilisateur", {}).get("langue", "français") if isinstance(c.get("utilisateur"), dict) else "français",
            })
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            return json_out(self, {"error": "JSON invalide."}, 400)

        if path == "/api/chats/new":
            return json_out(self, {"chat": create_chat()})

        if path == "/api/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                return json_out(self, {"error": "Message vide."}, 400)
            chat = get_chat(body.get("chat_id"))
            if chat is None:
                return json_out(self, {"error": "Conversation introuvable."}, 404)
            model = str(body.get("model") or model_from_config()).strip()
            models = installed_models()
            if models.get("error"):
                return json_out(self, {"error": "Ollama inaccessible : " + str(models["error"])}, 503)
            if not any(x["name"] == model for x in models["models"]):
                return json_out(self, {"error": f"Le modèle '{model}' n'est pas installé."}, 400)

            chat.setdefault("messages", []).append({"role": "user", "content": message})
            try:
                answer = chat_with_model(model, chat)
            except Exception as exc:
                chat["messages"].pop()
                return json_out(self, {"error": f"Erreur Ollama : {exc}"}, 502)
            chat["messages"].append({"role": "assistant", "content": answer})
            save_chat(chat)
            return json_out(self, {"ok": True, "answer": answer, "chat": chat})
        self.send_error(404)


def network_urls(port):
    urls = [f"http://127.0.0.1:{port}"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip != "0.0.0.0":
                url = f"http://{ip}:{port}"
                if url not in urls:
                    urls.append(url)
    except OSError:
        pass
    return urls


def run_server(port=8080):
    if not WEB_DIR.is_dir() or not (WEB_DIR / "index.html").is_file():
        raise RuntimeError(f"Interface web introuvable : {WEB_DIR}")
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("Le port doit être compris entre 1 et 65535.")

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("\n" + "=" * 60)
    print("LOCAL_IA — SERVEUR WEB")
    print("=" * 60)
    print(f"Écoute réseau : http://0.0.0.0:{port}")
    for url in network_urls(port):
        print(f"Adresse : {url}")
    print("Ctrl+C pour arrêter le serveur.")
    print("=" * 60 + "\n")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    try:
        # main.py peut transmettre directement le port lorsqu'il ouvre
        # une nouvelle invite de commande.
        if len(sys.argv) > 1:
            run_server(int(sys.argv[1]))
        else:
            value = input("Port HTTP (8080 par défaut) : ").strip()
            run_server(int(value) if value else 8080)
    except KeyboardInterrupt:
        print("\nServeur arrêté.")
    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)
