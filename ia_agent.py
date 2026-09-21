#!/usr/bin/env python3

import json
import sqlite3
import sys
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote


# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:1.5b"

DATA_DIR = Path.home() / ".ia_agent"
DB_PATH = DATA_DIR / "memory.db"

# context.json est placé dans le même dossier que ce script
CONTEXT_PATH = Path(__file__).resolve().parent / "context.json"

MAX_HISTORY = 12
MAX_MEMORIES = 20


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

    return f"""
Tu es {context.get("role", "un assistant personnel local")}.

Modèle utilisé :
{MODEL}


============================================================
CONFIGURATION DE L'ASSISTANT
============================================================

Langue :
{context.get("langue", "français")}

Sujet général :
{context.get("sujet", "assistant personnel généraliste")}

Ton :
{context.get("ton", "naturel, clair et concis")}

Style :
{context.get("style", "conversationnel")}


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

1. Utilise l'historique de conversation.
2. Utilise les souvenirs uniquement lorsqu'ils sont pertinents.
3. Ne prétends jamais connaître une information absente du contexte.
4. Si une information externe est fournie, distingue-la clairement
   de tes connaissances.
5. Si l'information externe semble incertaine, indique-le.
6. Respecte la langue définie dans context.json.
7. Respecte le ton défini dans context.json.
8. Respecte le style défini dans context.json.
9. Si le sujet change, adapte le contexte de conversation.
10. Ne répète pas inutilement les informations déjà connues.
11. Pour du code, donne du code directement utilisable.
"""


# ============================================================
# COMMANDES
# ============================================================

def show_help():
    print("""
Commandes disponibles :

  /help
      Affiche cette aide.

  /memory
      Affiche les souvenirs enregistrés.

  /remember <texte>
      Ajoute manuellement un souvenir.

  /topic
      Affiche le sujet actuel.

  /topic <sujet>
      Définit manuellement le sujet.

  /context
      Affiche le contexte chargé depuis context.json.

  /reload
      Recharge context.json sans redémarrer le programme.

  /search <recherche>
      Recherche des informations externes.

  /clear
      Efface l'historique de la conversation actuelle.

  /exit
      Quitte le programme.
""")


def show_context(context):
    print("\nContexte actuel :")
    print(json.dumps(
        context,
        ensure_ascii=False,
        indent=4
    ))
    print()


def clear_conversation(conn, conversation_id):
    conn.execute(
        """
        DELETE FROM messages
        WHERE conversation_id = ?
        """,
        (conversation_id,)
    )

    conn.commit()


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    conn = init_database()

    # --------------------------------------------------------
    # Chargement de context.json
    # --------------------------------------------------------

    context = load_context()

    # --------------------------------------------------------
    # Une conversation correspond à la session actuelle
    # --------------------------------------------------------

    conversation_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    topic = get_last_topic(conn)

    # --------------------------------------------------------
    # Interface
    # --------------------------------------------------------

    print("=" * 60)
    print(" IA AGENT LOCAL")
    print("=" * 60)

    print(f"Modèle   : {MODEL}")
    print(f"Mémoire  : {DB_PATH}")
    print(f"Contexte : {CONTEXT_PATH}")
    print(f"Langue   : {context.get('langue', 'non définie')}")
    print(f"Sujet    : {context.get('sujet', 'non défini')}")

    print()
    print("Tape /help pour afficher les commandes.")
    print("Tape /exit pour quitter.")
    print()

    # --------------------------------------------------------
    # Boucle principale
    # --------------------------------------------------------

    while True:

        try:
            user_message = input("Vous > ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir.")
            break

        if not user_message:
            continue

        # ====================================================
        # COMMANDES
        # ====================================================

        if user_message == "/exit":
            print("Au revoir.")
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
                print("Aucun souvenir.")

            else:
                print("\nMémoire :")

                for memory in memories:
                    print(f"- {memory}")

            continue

        # ----------------------------------------------------
        # /remember
        # ----------------------------------------------------

        if user_message.startswith("/remember "):

            memory = user_message[len("/remember "):].strip()

            if memory:
                save_memory(conn, memory)
                print("✓ Souvenir enregistré.")

            continue

        # ----------------------------------------------------
        # /topic
        # ----------------------------------------------------

        if user_message == "/topic":

            print(
                "Sujet actuel : "
                + (topic or "aucun")
            )

            continue

        # ----------------------------------------------------
        # /topic <sujet>
        # ----------------------------------------------------

        if user_message.startswith("/topic "):

            topic = user_message[len("/topic "):].strip()

            save_topic(conn, topic)

            print(f"✓ Sujet défini : {topic}")

            continue

        # ----------------------------------------------------
        # /context
        # ----------------------------------------------------

        if user_message == "/context":

            show_context(context)

            continue

        # ----------------------------------------------------
        # /reload
        # ----------------------------------------------------

        if user_message == "/reload":

            context = load_context()

            print("✓ context.json rechargé.")

            continue

        # ----------------------------------------------------
        # /search
        # ----------------------------------------------------

        if user_message.startswith("/search "):

            query = user_message[len("/search "):].strip()

            if not query:
                print("Utilisation : /search <recherche>")
                continue

            print("\nRecherche...")

            external_info = internet_search(query)

            print("\nRésultats :")
            print(external_info)
            print()

            continue

        # ----------------------------------------------------
        # /clear
        # ----------------------------------------------------

        if user_message == "/clear":

            clear_conversation(
                conn,
                conversation_id
            )

            print("✓ Conversation effacée.")

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
                "Analyse du sujet...",
                end="",
                flush=True
            )

            topic = detect_topic(user_message)

            save_topic(conn, topic)

            print(f" {topic}")

        # ====================================================
        # HISTORIQUE
        # ====================================================

        history = get_history(
            conn,
            conversation_id
        )

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

        messages.extend(history)

        messages.append(
            {
                "role": "user",
                "content": user_message
            }
        )

        # ====================================================
        # APPEL IA
        # ====================================================

        print("\nIA > ", end="", flush=True)

        answer = ask_ollama(messages)

        print(answer)
        print()

        # ====================================================
        # SAUVEGARDE
        # ====================================================

        save_message(
            conn,
            conversation_id,
            "user",
            user_message
        )

        save_message(
            conn,
            conversation_id,
            "assistant",
            answer
        )


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    main()
