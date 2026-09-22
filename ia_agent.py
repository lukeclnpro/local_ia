#!/usr/bin/env python3

import json
import os
import sqlite3
import sys
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

import ui
import perf


# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

def load_config():
    default_config = {"model": "qwen2.5:1.5b"}
    if not CONFIG_PATH.exists():
        print(f"Attention : {CONFIG_PATH} introuvable. Utilisation du modèle par défaut : {default_config["model"]}")
        return default_config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            config = json.load(file)
        if not isinstance(config, dict):
            print("Erreur : config.json doit contenir un objet JSON.")
            return default_config
        for key, value in default_config.items():
            if key not in config:
                config[key] = value
        if not isinstance(config["model"], str) or not config["model"].strip():
            print("Erreur : la clé 'model' de config.json doit être une chaîne non vide.")
            return default_config
        return config
    except json.JSONDecodeError as e:
        print(f"Erreur JSON dans config.json : {e}")
        return default_config
    except Exception as e:
        print(f"Impossible de charger config.json : {e}")
        return default_config

CONFIG = load_config()
MODEL = CONFIG["model"].strip()

DATA_DIR = Path.home() / ".ia_agent"
DB_PATH = DATA_DIR / "memory.db"

# context.json est placé dans le même dossier que ce script
CONTEXT_PATH = Path(__file__).resolve().parent / "context.json"

MAX_HISTORY = 12
MAX_MEMORIES = 20

# Chaque conversation est stockée dans un fichier JSON numéroté.
CHAT_DIR = Path(__file__).resolve().parent / "chats"


# ============================================================
# CONTEXTE
# ============================================================

def load_context():
    """
    Charge la configuration depuis context.json.

    Si le fichier n'existe pas ou contient une erreur,
    des valeurs par défaut sont utilisées.
    """

    default_context = {
        "langue": "français",
        "sujet": "assistant personnel généraliste",
        "ton": "naturel, clair et concis",
        "role": "assistant personnel local",
        "style": "conversationnel",
        "instructions": []
    }

    if not CONTEXT_PATH.exists():
        print(
            f"Attention : {CONTEXT_PATH} introuvable.\n"
            "Utilisation du contexte par défaut."
        )
        return default_context

    try:
        with open(CONTEXT_PATH, "r", encoding="utf-8") as file:
            context = json.load(file)

        if not isinstance(context, dict):
            print(
                "Erreur : context.json doit contenir un objet JSON."
            )
            return default_context

        # Complète les valeurs manquantes avec les valeurs par défaut
        for key, value in default_context.items():
            if key not in context:
                context[key] = value

        return context

    except json.JSONDecodeError as e:
        print(f"Erreur JSON dans context.json : {e}")
        return default_context

    except Exception as e:
        print(f"Impossible de charger context.json : {e}")
        return default_context


# ============================================================
# CONVERSATIONS
# ============================================================

def init_chats():
    """Crée le dossier chats s'il n'existe pas."""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)


def chat_path(chat_id):
    return CHAT_DIR / f"{chat_id}.json"


def get_next_chat_id():
    """Retourne le prochain numéro de conversation disponible."""
    init_chats()
    numbers = []
    for path in CHAT_DIR.glob("*.json"):
        if path.stem.isdigit():
            numbers.append(int(path.stem))
    return max(numbers, default=0) + 1


def create_chat():
    """Crée une nouvelle conversation JSON numérotée."""
    chat_id = get_next_chat_id()
    now = datetime.now().isoformat()
    chat = {
        "id": chat_id,
        "created_at": now,
        "updated_at": now,
        "summary": "",
        "topic": None,
        "messages": []
    }
    save_chat(chat)
    return chat


def save_chat(chat):
    """Sauvegarde une conversation complète dans chats/<numero>.json."""
    init_chats()
    chat["updated_at"] = datetime.now().isoformat()
    path = chat_path(chat["id"])
    with open(path, "w", encoding="utf-8") as file:
        json.dump(chat, file, ensure_ascii=False, indent=4)


def load_chat(chat_id):
    """Charge une conversation JSON existante."""
    path = chat_path(chat_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            chat = json.load(file)
        if not isinstance(chat, dict):
            return None
        chat.setdefault("id", chat_id)
        chat.setdefault("summary", "")
        chat.setdefault("topic", None)
        chat.setdefault("messages", [])
        return chat
    except (json.JSONDecodeError, OSError) as e:
        print(f"Erreur lors du chargement du chat {chat_id} : {e}")
        return None


def list_chats():
    """Retourne les conversations disponibles, par numéro décroissant."""
    init_chats()
    chats = []
    for path in CHAT_DIR.glob("*.json"):
        if path.stem.isdigit():
            chat = load_chat(int(path.stem))
            if chat:
                chats.append(chat)
    return sorted(chats, key=lambda c: int(c.get("id", 0)), reverse=True)


def get_chat_history(chat, limit=MAX_HISTORY):
    """Retourne les derniers messages au format attendu par Ollama."""
    messages = chat.get("messages", [])
    return [
        {"role": message["role"], "content": message["content"]}
        for message in messages[-limit:]
        if message.get("role") in {"user", "assistant"}
    ]


def add_chat_message(chat, role, content):
    """Ajoute un message au chat puis sauvegarde le fichier JSON."""
    chat.setdefault("messages", []).append({
        "role": role,
        "content": content,
        "created_at": datetime.now().isoformat()
    })
    save_chat(chat)


def clear_chat(chat):
    """Efface les messages du chat courant sans supprimer son fichier."""
    chat["messages"] = []
    chat["summary"] = ""
    chat["topic"] = None
    save_chat(chat)


# ============================================================
# RÉSUMÉ DE CONVERSATION
# ============================================================

def build_summary_prompt(previous_summary, user_message, assistant_message, context):
    """Construit le prompt utilisé pour mettre à jour le résumé."""
    language = str(context.get("langue", "français")).strip() or "français"

    previous = previous_summary.strip() or "(Aucun résumé précédent.)"

    return f"""
Tu mets à jour le résumé permanent d'une conversation.

LANGUE OBLIGATOIRE : {language}

OBJECTIF :
À partir du résumé précédent et du dernier échange, produis UN NOUVEAU
résumé complet qui remplace l'ancien. Le résumé doit conserver les
informations importantes de toute la conversation, pas seulement du
dernier échange.

RÈGLES :
- Commence par le résumé précédent et complète-le avec le nouvel échange.
- Supprime les détails devenus inutiles ou redondants.
- Conserve les décisions, objectifs, contraintes, préférences exprimées,
  informations techniques utiles, problèmes en cours et éléments à retenir.
- Ne fabrique aucune information.
- Si le dernier échange corrige une information précédente, conserve la
  version corrigée.
- Sois compact mais suffisamment précis pour permettre à une autre IA de
  poursuivre la conversation sans avoir les anciens messages sous les yeux.
- Retourne uniquement le résumé final, sans préambule, sans commentaire,
  sans Markdown inutile.

RÉSUMÉ PRÉCÉDENT :
{previous}

NOUVEAU MESSAGE UTILISATEUR :
{user_message}

NOUVELLE RÉPONSE DE L'IA :
{assistant_message}

RÉSUMÉ FINAL :
""".strip()


def update_chat_summary(chat, user_message, assistant_message, context):
    """
    Met à jour le résumé après chaque paire user/assistant.

    Le résumé est stocké directement dans le JSON de la conversation et
    remplacé à chaque nouveau message.
    """
    previous_summary = str(chat.get("summary", "") or "")

    prompt = build_summary_prompt(
        previous_summary=previous_summary,
        user_message=user_message,
        assistant_message=assistant_message,
        context=context,
    )

    try:
        new_summary = ask_ollama([
            {
                "role": "system",
                "content": (
                    "Tu es un module de synthèse de conversation. "
                    "Tu dois suivre exactement les instructions reçues "
                    "et retourner uniquement le nouveau résumé."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]).strip()

        if new_summary:
            chat["summary"] = new_summary
        else:
            chat["summary"] = previous_summary

    except Exception as error:
        ui.print_warn(f"Impossible de mettre à jour le résumé : {error}")
        chat["summary"] = previous_summary

    save_chat(chat)
    return chat["summary"]


# ============================================================
# BASE DE DONNÉES
# ============================================================

def init_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()

    return conn


# ============================================================
# MÉMOIRE
# ============================================================

def save_message(conn, conversation_id, role, content):
    conn.execute(
        """
        INSERT INTO messages
        (conversation_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            conversation_id,
            role,
            content,
            datetime.now().isoformat()
        )
    )

    conn.commit()


def get_history(conn, conversation_id, limit=MAX_HISTORY):
    cursor = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (conversation_id, limit)
    )

    rows = cursor.fetchall()
    rows.reverse()

    return [
        {
            "role": role,
            "content": content
        }
        for role, content in rows
    ]


def save_memory(conn, content):
    conn.execute(
        """
        INSERT INTO memories (content, created_at)
        VALUES (?, ?)
        """,
        (
            content,
            datetime.now().isoformat()
        )
    )

    conn.commit()


def get_memories(conn):
    cursor = conn.execute(
        """
        SELECT content
        FROM memories
        ORDER BY id DESC
        LIMIT ?
        """,
        (MAX_MEMORIES,)
    )

    return [row[0] for row in cursor.fetchall()]


def save_topic(conn, topic):
    conn.execute(
        """
        INSERT INTO topics (topic, created_at)
        VALUES (?, ?)
        """,
        (
            topic,
            datetime.now().isoformat()
        )
    )

    conn.commit()


def get_last_topic(conn):
    cursor = conn.execute(
        """
        SELECT topic
        FROM topics
        ORDER BY id DESC
        LIMIT 1
        """
    )

    row = cursor.fetchone()

    return row[0] if row else None


# ============================================================
# INFORMATIONS EXTERNES
# ============================================================

def internet_search(query):
    """
    Recherche simple via DuckDuckGo HTML.

    Ce n'est pas un moteur de recherche complet.
    L'objectif est seulement de donner à l'IA
    un contexte externe.
    """

    try:
        url = (
            "https://html.duckduckgo.com/html/?q="
            + quote(query)
        )

        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urlopen(request, timeout=10) as response:
            html = response.read().decode(
                "utf-8",
                errors="ignore"
            )

        results = []

        # Extraction basique des titres/descriptions
        pattern = re.compile(
            r'class="result__a"[^>]*>(.*?)</a>',
            re.S
        )

        matches = pattern.findall(html)

        for match in matches[:5]:
            text = re.sub("<.*?>", "", match)
            text = text.replace("&amp;", "&")
            results.append(text.strip())

        if not results:
            return "Aucun résultat externe trouvé."

        return "\n".join(
            f"- {result}"
            for result in results
        )

    except Exception as e:
        return f"Recherche externe indisponible : {e}"


# ============================================================
# OPTIMISATION DES MESSAGES
# ============================================================

def estimate_messages_size(messages):
    """Estime la taille textuelle des messages en caractères."""
    return sum(len(str(message.get("content", ""))) for message in messages)


def estimate_tokens(text):
    """Estimation approximative des tokens (environ 1 token / 4 caractères)."""
    return max(1, len(str(text)) // 4)


def merge_system_messages(messages):
    """Fusionne les messages système consécutifs en conservant leur contenu."""
    merged = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        content = str(message.get("content", "")).strip()

        if not content:
            continue

        if role == "system" and merged and merged[-1].get("role") == "system":
            merged[-1]["content"] += "\n\n" + content
        else:
            merged.append({"role": role, "content": content})

    return merged


def remove_duplicate_messages(messages):
    """Supprime les doublons exacts sans modifier l'ordre des messages."""
    result = []
    seen = set()

    for message in messages:
        key = (message.get("role"), message.get("content", "").strip())
        if key in seen:
            continue
        seen.add(key)
        result.append(message)

    return result


def _truncate_text(text, max_chars):
    """Réduit un texte en conservant son début et sa fin."""
    text = str(text)
    if len(text) <= max_chars:
        return text

    if max_chars < 100:
        return text[:max_chars]

    head = int(max_chars * 0.7)
    tail = max_chars - head
    return text[:head].rstrip() + "\n...[contexte réduit]...\n" + text[-tail:].lstrip()


def reduce_context(messages, max_chars):
    """
    Réduit progressivement les messages lorsque la taille maximale est dépassée.

    Priorités de conservation :
      1. dernier message utilisateur ;
      2. messages système ;
      3. résumé de conversation ;
      4. autres informations de contexte.
    """
    if estimate_messages_size(messages) <= max_chars:
        return messages

    result = [dict(message) for message in messages]

    # Le dernier message utilisateur est toujours conservé intégralement.
    last_user_index = None
    for index in range(len(result) - 1, -1, -1):
        if result[index].get("role") == "user":
            last_user_index = index
            break

    # Réduit d'abord les blocs système les plus longs, mais conserve les règles.
    system_indices = [
        index for index, message in enumerate(result)
        if message.get("role") == "system" and index != last_user_index
    ]

    while estimate_messages_size(result) > max_chars and system_indices:
        # Choisit le plus gros bloc système restant.
        index = max(system_indices, key=lambda i: len(result[i].get("content", "")))
        content = result[index].get("content", "")
        current_size = len(content)
        excess = estimate_messages_size(result) - max_chars
        target = max(800, current_size - excess)

        if target >= current_size:
            break

        result[index]["content"] = _truncate_text(content, target)
        system_indices.remove(index)

    # Si nécessaire, réduit le résumé de conversation.
    for index, message in enumerate(result):
        content = message.get("content", "")
        if "RÉSUMÉ DE LA CONVERSATION À UTILISER COMME CONTEXTE :" in content:
            if estimate_messages_size(result) > max_chars:
                excess = estimate_messages_size(result) - max_chars
                target = max(500, len(content) - excess)
                result[index]["content"] = _truncate_text(content, target)
            break

    # Dernier filet de sécurité : réduit les blocs non prioritaires.
    while estimate_messages_size(result) > max_chars:
        candidates = [
            index for index, message in enumerate(result)
            if index != last_user_index
            and message.get("role") != "user"
            and len(message.get("content", "")) > 500
        ]

        if not candidates:
            break

        index = max(candidates, key=lambda i: len(result[i].get("content", "")))
        excess = estimate_messages_size(result) - max_chars
        current = len(result[index].get("content", ""))
        target = max(300, current - excess)
        result[index]["content"] = _truncate_text(result[index]["content"], target)

        if target >= current:
            break

    return result


def optimize_messages(messages, max_chars=12000):
    """
    Optimise les messages avant leur envoi à Ollama.

    Étapes : fusion des blocs système, suppression des doublons,
    puis réduction progressive du contexte si la taille maximale est dépassée.
    """
    original_size = estimate_messages_size(messages)

    optimized = merge_system_messages(messages)
    optimized = remove_duplicate_messages(optimized)
    optimized = reduce_context(optimized, max_chars)

    optimized_size = estimate_messages_size(optimized)
    saved = max(0, original_size - optimized_size)
    reduction = (saved / original_size * 100) if original_size else 0

    stats = {
        "original_chars": original_size,
        "optimized_chars": optimized_size,
        "saved_chars": saved,
        "reduction_percent": round(reduction, 1),
        "estimated_tokens": estimate_tokens("".join(
            str(message.get("content", "")) for message in optimized
        )),
    }

    return optimized, stats


# ============================================================
# OLLAMA
# ============================================================

def ask_ollama(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")

    request = Request(
        OLLAMA_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlopen(request, timeout=300) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        return result["message"]["content"]

    except Exception as e:
        return (
            "Erreur lors de la communication avec Ollama.\n"
            f"{e}"
        )


# ============================================================
# DÉTECTION DU SUJET
# ============================================================

def detect_topic(user_message):
    """
    Demande à Qwen de proposer un sujet court.
    """

    prompt = [
        {
            "role": "system",
            "content": (
                "Tu es un classificateur de sujet. "
                "Donne uniquement un sujet très court "
                "(2 à 6 mots), sans explication."
            )
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    topic = ask_ollama(prompt)

    topic = topic.strip()
    topic = topic.replace("\n", " ")

    return topic[:100]


# ============================================================
# EXTRACTION DE MÉMOIRE
# ============================================================

def detect_memory(user_message):
    """
    Détecte si l'utilisateur donne une information
    qui pourrait être utile dans les futures discussions.
    """

    keywords = [
        "je m'appelle",
        "mon nom est",
        "je suis",
        "j'habite",
        "je travaille",
        "mon projet",
        "je préfère",
        "j'aime",
        "je n'aime pas",
        "rappelle-toi",
        "souviens-toi",
        "à retenir"
    ]

    text = user_message.lower()

    for keyword in keywords:
        if keyword in text:
            return user_message

    return None


# ============================================================
# CONSTRUCTION DU CONTEXTE
# ============================================================

def build_system_prompt(
    memories,
    topic,
    context,
    external_info=None
):
    """
    Construit le prompt système à partir de :

    - context.json
    - mémoire utilisateur
    - sujet actuel
    - informations externes
    """

    memory_text = "\n".join(
        f"- {memory}"
        for memory in memories
    )

    if not memory_text:
        memory_text = "Aucune mémoire enregistrée."

    external_text = external_info or (
        "Aucune information externe utilisée."
    )

    # --------------------------------------------------------
    # Instructions personnalisées
    # --------------------------------------------------------

    instructions = context.get("instructions", [])

    if isinstance(instructions, list):
        instructions_text = "\n".join(
            f"- {instruction}"
            for instruction in instructions
        )
    else:
        instructions_text = str(instructions)

    if not instructions_text:
        instructions_text = "Aucune instruction spécifique."

    # --------------------------------------------------------
    # Construction du prompt
    # --------------------------------------------------------

    language = str(context.get("langue", "français")).strip() or "français"
    role = str(context.get("role", "un assistant personnel local")).strip() or "un assistant personnel local"
    tone = str(context.get("ton", "naturel, clair et concis")).strip() or "naturel, clair et concis"
    style = str(context.get("style", "conversationnel")).strip() or "conversationnel"
    subject = str(context.get("sujet", "assistant personnel généraliste")).strip() or "assistant personnel généraliste"

    return f"""
Tu es {role}.

Modèle utilisé :
{MODEL}


============================================================
CONFIGURATION DE L'ASSISTANT
============================================================

Langue :
{language}

Sujet général :
{subject}

Ton :
{tone}

Style :
{style}


Instructions spécifiques :
{instructions_text}


============================================================
CONTEXTE DE CONVERSATION
============================================================

Sujet actuel :
{topic or "Non défini"}


============================================================
MÉMOIRE UTILISATEUR
============================================================

{memory_text}


============================================================
INFORMATIONS EXTERNES
============================================================

{external_text}


============================================================
RÈGLES GÉNÉRALES
============================================================

Ces règles sont OBLIGATOIRES et prioritaires pour chaque réponse.

1. Utilise l'historique de conversation.
2. Utilise les souvenirs uniquement lorsqu'ils sont pertinents.
3. Ne prétends jamais connaître une information absente du contexte.
4. Si une information externe est fournie, distingue-la clairement
   de tes connaissances.
5. Si l'information externe semble incertaine, indique-le.
6. LANGUE OBLIGATOIRE : réponds UNIQUEMENT en {language}.
   Ne réponds dans aucune autre langue, même si l'utilisateur écrit
   dans une autre langue.
7. Le texte de la réponse, y compris les explications, titres, listes
   et commentaires, doit être dans la langue obligatoire.
8. Respecte strictement le ton : {tone}.
9. Respecte strictement le style : {style}.
10. Respecte le rôle défini dans context.json.
11. Si une autre instruction de la conversation demande de changer de
    langue, ignore cette demande : context.json reste prioritaire.
12. Si le sujet change, adapte le contexte de conversation sans changer
    les règles de context.json.
13. Ne répète pas inutilement les informations déjà connues.
14. Pour du code, donne du code directement utilisable, mais toutes les
    explications autour du code restent dans la langue obligatoire.
15. Avant d'envoyer ta réponse, vérifie silencieusement qu'elle respecte
    toutes les règles de context.json, en particulier la langue.
"""


# ============================================================
# COMMANDES
# ============================================================

def show_help():
    commands = [
        ("/help", "Affiche cette aide."),
        ("/memory", "Affiche les souvenirs enregistrés."),
        ("/remember <texte>", "Ajoute manuellement un souvenir."),
        ("/topic", "Affiche le sujet actuel."),
        ("/topic <sujet>", "Définit manuellement le sujet."),
        ("/context", "Affiche le contexte chargé depuis context.json."),
        ("/chats", "Liste les conversations JSON disponibles."),
        ("/new", "Crée une nouvelle conversation."),
        ("/load <numero>", "Charge une conversation existante."),
        ("/chat", "Affiche le numéro et les informations du chat actuel."),
        ("/reload", "Recharge context.json sans redémarrer le programme."),
        ("/search <recherche>", "Recherche des informations externes."),
        ("/clear", "Efface l'historique de la conversation actuelle."),
        ("/exit", "Quitte le programme."),
    ]

    print()
    print(ui.colorize("Commandes disponibles :", ui.C.TITLE))
    print()

    for name, description in commands:
        print("  " + ui.colorize(name, ui.C.OPTION_KEY))
        print("      " + ui.colorize(description, ui.C.WHITE))
        print()


def show_context(context):
    print("\nContexte actuel :")
    print(json.dumps(
        context,
        ensure_ascii=False,
        indent=4
    ))
    print()


# ============================================================
# AFFICHAGE DES MESSAGES (COULEURS + HORODATAGE)
# ============================================================

def render_message(role, content, created_at=None):
    """
    Affiche un message (utilisateur ou IA) avec :
        - un libellé coloré
        - la date et l'heure
        - le contenu du message
    """

    timestamp = ui.format_timestamp(created_at)

    if role == "user":
        label = "Vous"
        color = ui.C.USER
    else:
        label = "IA"
        color = ui.C.IA

    header = (
        ui.colorize(f"{label}", color)
        + "  "
        + ui.colorize(f"[{timestamp}]", ui.C.TIME)
    )

    print(header)
    print(content)
    print()


def replay_history(chat):
    """
    Réaffiche l'historique complet d'une conversation, dans l'ordre
    chronologique (les anciens messages en haut), avec couleurs et
    horodatage, comme dans une vraie interface de chat.
    """

    messages = chat.get("messages", [])

    if not messages:
        return

    print(ui.hr())
    print(
        ui.colorize(
            f"  Historique de la conversation {chat['id']} "
            f"({len(messages)} messages)",
            ui.C.SUBTITLE,
        )
    )
    print(ui.hr())
    print()

    for message in messages:
        role = message.get("role")

        if role not in ("user", "assistant"):
            continue

        render_message(
            role,
            message.get("content", ""),
            message.get("created_at"),
        )

    print(ui.hr())
    print(ui.colorize("  Fin de l'historique — la conversation continue ci-dessous", ui.C.SUBTITLE))
    print(ui.hr())
    print()


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    global CONFIG, MODEL

    conn = init_database()

    # --------------------------------------------------------
    # Chargement de context.json
    # --------------------------------------------------------

    context = load_context()

    # Valeurs du contexte utilisées à chaque réponse.
    language = str(context.get("langue", "français")).strip() or "français"
    tone = str(context.get("ton", "naturel, clair et concis")).strip() or "naturel, clair et concis"
    style = str(context.get("style", "conversationnel")).strip() or "conversationnel"

    # --------------------------------------------------------
    # Sélection de la conversation demandée par main.py
    # --------------------------------------------------------

    init_chats()

    chat_mode = os.environ.get("IA_AGENT_CHAT_MODE", "new")
    requested_chat_id = os.environ.get("IA_AGENT_CHAT_ID")

    chat = None

    if chat_mode == "load" and requested_chat_id and requested_chat_id.isdigit():
        chat = load_chat(int(requested_chat_id))

        if chat is None:
            ui.print_warn(
                f"Conversation {requested_chat_id} introuvable. "
                "Une nouvelle conversation va être créée."
            )

    if chat is None:
        chat = create_chat()

    conversation_id = chat["id"]
    topic = chat.get("topic")

    # --------------------------------------------------------
    # Interface
    # --------------------------------------------------------

    ui.clear_screen()
    ui.section_title("IA AGENT LOCAL", clear=False)

    def info_line(label, value):
        print(
            ui.colorize(f"{label:<10}: ", ui.C.SUBTITLE)
            + ui.colorize(str(value), ui.C.WHITE)
        )

    info_line("Modèle", MODEL)
    info_line("Mémoire", DB_PATH)
    info_line("Contexte", CONTEXT_PATH)
    info_line("Config", CONFIG_PATH)
    info_line("Chats", CHAT_DIR)
    info_line("Chat", conversation_id)
    info_line("Langue", context.get('langue', 'non définie'))
    info_line("Sujet", context.get('sujet', 'non défini'))

    print()
    print(ui.colorize("Tape /help pour afficher les commandes.", ui.C.INFO))
    print(ui.colorize("Tape /exit pour quitter.", ui.C.INFO))
    print()

    # --------------------------------------------------------
    # Réaffichage de l'historique (anciens messages en haut,
    # avec date, heure et couleurs).
    # --------------------------------------------------------

    replay_history(chat)

    # --------------------------------------------------------
    # Boucle principale
    # --------------------------------------------------------

    while True:

        prompt_header = (
            ui.colorize("Vous", ui.C.USER)
            + "  "
            + ui.colorize(f"[{ui.format_timestamp()}]", ui.C.TIME)
        )

        try:
            print(prompt_header)
            user_message = input(
                ui.colorize("> ", ui.C.USER)
            ).strip()

        except (KeyboardInterrupt, EOFError):
            print(ui.colorize("\nAu revoir.", ui.C.INFO))
            break

        if not user_message:
            continue

        # ====================================================
        # COMMANDES
        # ====================================================

        if user_message == "/exit":
            print(ui.colorize("Au revoir.", ui.C.INFO))
            break

        if user_message == "/help":
            show_help()
            continue

        # ----------------------------------------------------
        # /memory
        # ----------------------------------------------------

        if user_message == "/memory":

            memories = get_memories(conn)

            if not memories:
                ui.print_info("Aucun souvenir.")

            else:
                print()
                print(ui.colorize("Mémoire :", ui.C.SUBTITLE))

                for memory in memories:
                    print(ui.colorize(f"- {memory}", ui.C.WHITE))

            continue

        # ----------------------------------------------------
        # /remember
        # ----------------------------------------------------

        if user_message.startswith("/remember "):

            memory = user_message[len("/remember "):].strip()

            if memory:
                save_memory(conn, memory)
                ui.print_ok("Souvenir enregistré.")

            continue

        # ----------------------------------------------------
        # /topic
        # ----------------------------------------------------

        if user_message == "/topic":

            print(
                ui.colorize("Sujet actuel : ", ui.C.SUBTITLE)
                + ui.colorize(topic or "aucun", ui.C.WHITE)
            )

            continue

        # ----------------------------------------------------
        # /topic <sujet>
        # ----------------------------------------------------

        if user_message.startswith("/topic "):

            topic = user_message[len("/topic "):].strip()

            chat["topic"] = topic
            save_chat(chat)

            ui.print_ok(f"Sujet défini : {topic}")

            continue

        # ----------------------------------------------------
        # /context
        # ----------------------------------------------------

        if user_message == "/context":

            show_context(context)

            continue

        # ----------------------------------------------------
        # /chat
        # ----------------------------------------------------

        if user_message == "/chat":
            print()
            print(ui.colorize(f"Chat actuel : {chat['id']}", ui.C.SUBTITLE))
            print(ui.colorize(f"Créé        : {chat.get('created_at', 'inconnu')}", ui.C.WHITE))
            print(ui.colorize(f"Messages    : {len(chat.get('messages', []))}", ui.C.WHITE))
            print(ui.colorize(f"Sujet       : {chat.get('topic') or 'aucun'}", ui.C.WHITE))
            print()
            continue

        # ----------------------------------------------------
        # /chats
        # ----------------------------------------------------

        if user_message == "/chats":
            chats = list_chats()
            print()
            print(ui.colorize("Conversations disponibles :", ui.C.SUBTITLE))
            if not chats:
                ui.print_info("Aucune conversation.")
            else:
                for item in chats:
                    marker = ui.colorize(" <== actuelle", ui.C.OK) if item["id"] == chat["id"] else ""
                    topic_text = item.get("topic") or "sans sujet"
                    print(
                        ui.colorize(
                            f"  {item['id']} | {topic_text} | "
                            f"{len(item.get('messages', []))} messages",
                            ui.C.WHITE,
                        )
                        + marker
                    )
            print()
            continue

        # ----------------------------------------------------
        # /new
        # ----------------------------------------------------

        if user_message == "/new":
            chat = create_chat()
            conversation_id = chat["id"]
            topic = None
            ui.clear_screen()
            ui.print_ok(f"Nouvelle conversation : {conversation_id}")
            continue

        # ----------------------------------------------------
        # /load <numero>
        # ----------------------------------------------------

        if user_message.startswith("/load "):
            value = user_message[len("/load "):].strip()
            if not value.isdigit():
                ui.print_info("Utilisation : /load <numero>")
                continue

            loaded_chat = load_chat(int(value))
            if loaded_chat is None:
                ui.print_error(f"Conversation introuvable : {value}")
                continue

            chat = loaded_chat
            conversation_id = chat["id"]
            topic = chat.get("topic")
            ui.clear_screen()
            replay_history(chat)
            ui.print_ok(f"Conversation {conversation_id} chargée.")
            continue

        # ----------------------------------------------------
        # /reload
        # ----------------------------------------------------

        if user_message == "/reload":

            CONFIG = load_config()
            MODEL = CONFIG["model"].strip()
            context = load_context()
            language = str(context.get("langue", "français")).strip() or "français"
            tone = str(context.get("ton", "naturel, clair et concis")).strip() or "naturel, clair et concis"
            style = str(context.get("style", "conversationnel")).strip() or "conversationnel"

            ui.print_ok(f"Configuration rechargée. Modèle : {MODEL}")

            continue

        # ----------------------------------------------------
        # /search
        # ----------------------------------------------------

        if user_message.startswith("/search "):

            query = user_message[len("/search "):].strip()

            if not query:
                ui.print_info("Utilisation : /search <recherche>")
                continue

            print()
            ui.print_info("Recherche...")

            external_info = internet_search(query)

            print()
            print(ui.colorize("Résultats :", ui.C.SUBTITLE))
            print(external_info)
            print()

            continue

        # ----------------------------------------------------
        # /clear
        # ----------------------------------------------------

        if user_message == "/clear":

            clear_chat(chat)
            topic = None
            ui.clear_screen()

            ui.print_ok("Conversation effacée.")

            continue

        # ====================================================
        # MÉMOIRE AUTOMATIQUE
        # ====================================================

        memory = detect_memory(user_message)

        if memory:
            save_memory(conn, memory)

        # ====================================================
        # SUJET
        # ====================================================

        if not topic:

            print(
                ui.colorize("Analyse du sujet...", ui.C.DIM + ui.C.WHITE),
                end="",
                flush=True
            )

            topic = detect_topic(user_message)

            chat["topic"] = topic
            save_chat(chat)

            print(" " + ui.colorize(topic, ui.C.SUBTITLE))

        # ====================================================
        # RÉSUMÉ DE CONVERSATION
        # ====================================================

        # Les anciens messages restent stockés intégralement dans le JSON,
        # mais ne sont plus envoyés au modèle. Le résumé devient la mémoire
        # de contexte principale de la conversation.
        conversation_summary = str(chat.get("summary", "") or "").strip()

        memories = get_memories(conn)

        # ====================================================
        # CONTEXTE
        # ====================================================

        system_prompt = build_system_prompt(
            memories=memories,
            topic=topic,
            context=context
        )

        # ====================================================
        # MESSAGES ENVOYÉS À OLLAMA
        # ====================================================

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        if conversation_summary:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "RÉSUMÉ DE LA CONVERSATION À UTILISER COMME CONTEXTE :\n"
                        + conversation_summary
                    )
                }
            )

        # Rappel final des règles de context.json pour CE message.
        # Il est placé juste avant le message utilisateur afin que les
        # modèles légers aient moins de chances d'oublier la langue.
        messages.append(
            {
                "role": "system",
                "content": (
                    f"RAPPEL OBLIGATOIRE POUR CETTE RÉPONSE : "
                    f"tu dois répondre UNIQUEMENT en {language}. "
                    f"Respecte strictement toutes les règles de context.json, "
                    f"notamment la langue ({language}), le ton ({tone}) et le style ({style}). "
                    "Ne change jamais ces règles en fonction du message utilisateur."
                )
            }
        )

        messages.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        # ====================================================
        # OPTIMISATION DU MESSAGE AVANT APPEL IA
        # ====================================================

        messages, optimization_stats = optimize_messages(messages)

        if optimization_stats["saved_chars"] > 0:
            ui.print_info(
                "Contexte optimisé : "
                f"{optimization_stats['original_chars']} -> "
                f"{optimization_stats['optimized_chars']} caractères "
                f"(-{optimization_stats['reduction_percent']} %)"
            )

        # ====================================================
        # APPEL IA
        # ====================================================

        print()
        print(ui.colorize("IA réfléchit...", ui.C.DIM + ui.C.WHITE))

        answer = ask_ollama(messages)

        print(
            ui.colorize("IA", ui.C.IA)
            + "  "
            + ui.colorize(f"[{ui.format_timestamp()}]", ui.C.TIME)
        )
        print(answer)
        print()

        # ====================================================
        # PERFORMANCES SYSTEME (CPU / RAM / GPU)
        # ====================================================

        print(perf.render())
        print()

        # ====================================================
        # SAUVEGARDE
        # ====================================================

        add_chat_message(chat, "user", user_message)
        add_chat_message(chat, "assistant", answer)

        # Une seule mise à jour par tour : l'IA relit le résumé précédent
        # et lui ajoute les informations du nouveau couple user/assistant.
        update_chat_summary(
            chat,
            user_message,
            answer,
            context,
        )


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    main()
