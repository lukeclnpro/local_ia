Voici le contenu prêt à mettre dans `README.md` :

````markdown
# Local IA

Installation et lancement de **Local IA** sur CachyOS et Windows.

## 🐧 CachyOS

### 1. Cloner le dépôt

```bash
git clone https://github.com/lukeclnpro/local_ia.git
cd local_ia
````

### 2. Installer les dépendances système

```bash
sudo pacman -Syu --needed --noconfirm python python-pip python-virtualenv curl git base-devel
```

### 3. Tester Ollama

```bash
python ollama_test.py
```

### 4. Activer Ollama

```bash
sudo systemctl enable --now ollama
```

### 5. Télécharger le modèle Qwen

```bash
ollama pull qwen2.5:1.5b
```

### 6. Créer l'environnement virtuel Python

```bash
python3 -m venv .venv
```

### 7. Activer l'environnement virtuel

Pour Fish :

```fish
. .venv/bin/activate.fish
```

### 8. Mettre à jour pip

```bash
python -m pip install --upgrade pip
```

### 9. Rendre le script exécutable

```bash
chmod +x ia_agent.py
```

### 10. Lancer Local IA

```bash
python ia_agent.py
```

---

## 🪟 Windows

### 1. Cloner le dépôt

```powershell
git clone https://github.com/lukeclnpro/local_ia.git
cd local_ia
```

### 2. Autoriser l'exécution des scripts PowerShell

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Tester Ollama

```powershell
python ollama_test.py
```

### 4. Installer Python, Git et Ollama

Avec `winget` :

```powershell
winget install Python.Python.3 Git.Git Ollama.Ollama
```

### 5. Télécharger le modèle Qwen

```powershell
ollama pull qwen2.5:1.5b
```

### 6. Créer l'environnement virtuel Python

```powershell
python -m venv .venv
```

### 7. Activer l'environnement virtuel

```powershell
.venv\Scripts\Activate.ps1
```

### 8. Mettre à jour pip

```powershell
python -m pip install --upgrade pip
```

### 9. Lancer Local IA

```powershell
python ia_agent.py
```

---

## 🤖 Modèle utilisé

Local IA utilise **Ollama** avec le modèle :

```text
qwen2.5:1.5b
```

## 📁 Structure

Après l'installation, le projet contient notamment :

```text
local_ia/
├── .venv/
├── ia_agent.py
├── ollama_test.py
└── README.md
```

## 🔄 Mise à jour du projet

Pour récupérer les dernières modifications :

```bash
git pull
```

Sous Windows PowerShell :

```powershell
git pull
```

```

**Note :** j’ai corrigé la commande Windows d’activation en `.venv\Scripts\Activate.ps1` (il manquait le `\` après `.venv` dans ta version).
```
