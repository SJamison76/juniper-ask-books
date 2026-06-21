# Juniper Day One - Ask Books

A local system for querying Juniper Day One books using natural language. Ask questions about Junos OS configuration and get answers with actual CLI commands and config examples pulled directly from the books.

Includes an interactive chat mode for follow-up questions, an AI configurator that connects to live devices and applies changes, and an offline config auditor that critiques configs against the books without touching any device.

---

## How It Works

1. PDF books are chunked and embedded into a local ChromaDB vector database using
   the all-minilm embedding model running in Ollama. PyMuPDF is used for text
   extraction to preserve whitespace, indentation, and Junos config block structure.
   Chunking is line-aware so set commands and config stanzas are never split mid-line.

2. When you ask a question, the query is embedded and used to find the most
   semantically relevant chunks from the books.

3. The relevant chunks are passed as context to Claude (claude-sonnet-4-6) via the
   Anthropic API, which generates a focused answer with actual Junos CLI commands.

Embeddings and retrieval run locally. Answer generation requires an internet connection
to reach the Anthropic API. Your PDF content is sent to Anthropic only as part of the
query context. Prompt caching is used across all scripts to reduce API costs on
repeated queries.

---

## Requirements

- Ubuntu 22.04 or later (tested on Ubuntu 26.04 LTS, kernel 7.0)
- Python 3.10 or later
- Ollama 0.30.9 or later (for embeddings only)
- 16GB RAM minimum (32GB recommended)
- Juniper Day One PDF books placed in /srv/ftp/dayone
- Anthropic API key (see API Key Setup below)

---

## API Key Setup

Answer generation uses the Anthropic API. You need an API key from console.anthropic.com.

The key is loaded from your shell environment. Add it to ~/.bashrc so it is available
at every login:

    echo "export ANTHROPIC_API_KEY='sk-ant-...'" >> ~/.bashrc
    source ~/.bashrc

Never hardcode the key in any script or commit it to git. The .gitignore already
excludes .env files if you prefer to store the key there instead.

Note: The Anthropic API is a separate paid service from a Claude.ai subscription.
Costs are minimal — approximately $0.03 to $0.06 per query with prompt caching enabled.

---

## Setup

Place your Juniper Day One PDF books in /srv/ftp/dayone, then run:

    chmod +x setup.sh
    ./setup.sh

This will:
- Create a Python virtual environment
- Install all dependencies including the Anthropic SDK, PyMuPDF, and PyEZ
- Pull the all-minilm embedding model via Ollama
- Index all PDFs into the ChromaDB vector database using PyMuPDF for accurate
  text extraction with preserved formatting and line-aware chunking

Indexing 36 books takes approximately 10 to 20 minutes. Progress is saved after
each book so if the process is interrupted it will resume where it left off.

If you add new books or want to reindex from scratch:

    rm -rf ~/juniper_vector_db ~/juniper_index_checkpoint.json
    ./juniper-env/bin/python index_books.py

---

## Usage: ask_books.py

Ask any question about Junos OS in plain English. Supports both single question
mode and an interactive chat loop with conversation history.

Single question mode:

    ./juniper-env/bin/python ask_books.py "your question here"

Interactive chat mode (follow-up questions, conversation history maintained):

    ./juniper-env/bin/python ask_books.py

Examples:

    ./juniper-env/bin/python ask_books.py "how do I configure a BGP neighbor?"
    ./juniper-env/bin/python ask_books.py "show me OSPF area configuration on Junos"
    ./juniper-env/bin/python ask_books.py "how do I configure EVPN VXLAN on an EX switch?"

Example interactive session:

    $ ./juniper-env/bin/python ask_books.py
    ╔══════════════════════════════════════════════════════════╗
    ║         Juniper Day One - Interactive Q&A                ║
    ║  Ask questions about Junos OS. Type 'exit' to quit.      ║
    ╚══════════════════════════════════════════════════════════╝

    Ask a question (or 'exit' to quit): how do I configure OSPF?

    📖 Found 10 relevant chunk(s). Asking Claude...
    💾 Cache written: 1842 tokens cached for next run

    ============================================================
    ANSWER:
    ============================================================
    EXAMPLE CONFIG:
    set protocols ospf area 0 interface ge-0/0/0.0
    set protocols ospf area 0 interface ge-0/0/1.0

    set protocols ospf area 0 interface ge-0/0/0.0
      Places ge-0/0/0.0 into OSPF area 0. The .0 is the logical unit number.

    set protocols ospf area 0 interface ge-0/0/1.0
      Does the same for the second uplink interface.
    ============================================================
    SOURCES:
      Junos4IOS book.pdf — p.21, p.29
      junos-beginners-guide.pdf — p.227
    ============================================================

    Ask a question (or 'exit' to quit): how do I add authentication to that?

    📖 Found 10 relevant chunk(s). Asking Claude...
    💾 Cache hit: 1842 tokens read from cache

    ...

---

## Usage: critique_config.py

Offline config auditor. Reads a config file and critiques it against the indexed
Day One books. No device connection required. Safe to use on any config.

    ./juniper-env/bin/python critique_config.py <config.txt> [focus]

Examples:

    ./juniper-env/bin/python critique_config.py config.txt
    ./juniper-env/bin/python critique_config.py config.txt "harden this config"
    ./juniper-env/bin/python critique_config.py config.txt "review BGP configuration"
    ./juniper-env/bin/python critique_config.py config.txt "check OSPF setup"

If no focus is given a general best-practice review is performed.

To pull a config from a device for review:

    ssh admin@192.168.1.1 "show configuration | display set" > config.txt
    ./juniper-env/bin/python critique_config.py config.txt "harden this config"

Output is structured as four sections — Summary, Issues (with fix commands),
Recommendations, and Correct. At the end you are offered the option to save
the critique to a text file.

Example output:

    ============================================================
     CRITIQUE: config.txt
    ============================================================
    SUMMARY
    Config has 11 hardening issues. Critical gaps include XNM clear-text,
    no PROTECT-RE filter, and world-readable log files.

    ISSUES

    ISSUE 1: XNM cleartext enabled
    delete system services xnm-clear-text
    Cleartext management protocol exposes credentials on the wire.

    ISSUE 2: No SSH hardening configured
    set system services ssh root-login deny
    set system services ssh connection-limit 5
    set system services ssh rate-limit 5
    Root can log in directly; no connection rate limiting in place.

    ...

    CORRECT
    Login classes have idle-timeout and login-alarms configured.
    NETCONF configured with rfc-compliant and yang-compliant flags.
    Syslog captures auth, firewall, and interactive-commands events.
    ============================================================

---

## Usage: do_configure.py

WARNING: This script connects to a live device and can apply configuration changes.
Use in a lab environment only. Always review the proposed changes before confirming.
A human should always review the output — this tool assists engineers, it does not
replace them.

do_configure.py works in two passes:

Pass 1 — Claude analyses the task and the current device config, then asks you for
any site-specific values it needs such as NTP server IPs, syslog servers, TACACS+
credentials, management subnets, SNMP community strings, and login banners. Optional
items can be left blank and will be skipped.

Pass 2 — Claude generates the full set of Junos commands using your answers, cross-
referenced against the indexed Day One books. The script runs a commit check on the
device and shows you the proposed changes before asking for confirmation. Nothing is
applied until you type yes.

Requires NETCONF enabled on the device:

    set system services netconf ssh

Run it:

    ./juniper-env/bin/python do_configure.py <device-ip> "what you want to do"

Examples:

    ./juniper-env/bin/python do_configure.py 192.168.1.1 "harden this switch"
    ./juniper-env/bin/python do_configure.py 192.168.1.1 "configure OSPF on all uplink interfaces"
    ./juniper-env/bin/python do_configure.py 192.168.1.1 "set up NTP with authentication"
    ./juniper-env/bin/python do_configure.py 192.168.1.1 "disable unused services and secure SSH"

Claude reads the current config before generating commands so it only produces
changes for things not already configured. The commit check validates the config
on the device before anything is applied, and the script rolls back automatically
if the commit fails.

Always review the warnings section — some commands may be skipped if values were
not provided or if the sanitiser detected invalid syntax.

---

## File Structure

    juniper-ask-books/
    |-- ask_books.py              Query the books — single question or interactive chat
    |-- critique_config.py        Offline config auditor — no device connection needed
    |-- do_configure.py           AI configurator — reads device and applies changes
    |-- index_books.py            Index PDF books into ChromaDB via PyMuPDF
    |-- requirements.txt          Python dependencies
    |-- setup.sh                  Automated setup script
    |-- .gitignore                Excludes venv, database, and PDFs from git
    |-- README.md                 This file
    |-- juniper-env/              Python virtual environment (not committed)
    |-- juniper_vector_db/        ChromaDB vector database (not committed)
    |-- juniper_index_checkpoint.json  Indexing progress tracker (not committed)

---

## Re-indexing

To re-index from scratch (for example after adding new books or after upgrading
index_books.py):

    rm -rf ~/juniper_vector_db ~/juniper_index_checkpoint.json
    ./juniper-env/bin/python index_books.py

Note: DB_PATH and CHECKPOINT_FILE in index_books.py default to your home directory.
If you are running as a different user, update those paths at the top of the script.

To add new books without re-indexing existing ones, just place the new PDFs in
/srv/ftp/dayone and re-run index_books.py. Already indexed books will be skipped.

---

## Configuration

Key settings are at the top of each script:

index_books.py:
- BOOK_DIR       Path to PDF books (default /srv/ftp/dayone)
- DB_PATH        Path to ChromaDB database (default ~/juniper_vector_db)
- CHUNK_SIZE     Max characters per chunk (default 1200)
- CHUNK_STEP     Overlap step between chunks (default 900)

ask_books.py:
- TOP_K          Number of chunks to keep after filtering (default 10)
- FETCH_K        Number of candidates to fetch before filtering (default 20)
- MAX_CONTEXT    Max characters of context sent to Claude (default 14000)
- MIN_RELEVANCE  L2 distance threshold, lower is stricter (default 1.2)
- CLAUDE_MODEL   Anthropic model to use (default claude-sonnet-4-6)

critique_config.py:
- TOP_K          Number of chunks to keep after filtering (default 12)
- FETCH_K        Number of candidates to fetch before filtering (default 24)
- MAX_CONTEXT    Max characters of book context sent to Claude (default 12000)
- MIN_RELEVANCE  L2 distance threshold, lower is stricter (default 1.2)
- CLAUDE_MODEL   Anthropic model to use (default claude-sonnet-4-6)

do_configure.py:
- TOP_K          Number of chunks to keep after filtering (default 12)
- FETCH_K        Number of candidates to fetch before filtering (default 24)
- MAX_CONTEXT    Max characters of book context sent to Claude (default 12000)
- MIN_RELEVANCE  L2 distance threshold, lower is stricter (default 1.2)
- CLAUDE_MODEL   Anthropic model to use (default claude-sonnet-4-6)
- NETCONF_PORT   NETCONF port (default 830)

---

## Models Used

- all-minilm         Embedding model, runs locally via Ollama, fast on CPU
- claude-sonnet-4-6  Language model for answer generation, via Anthropic API

---

## Tested On

- Hardware:  AMD Ryzen 7, 32GB RAM
- OS:        Ubuntu 26.04 LTS, kernel 7.0.0-22-generic
- Ollama:    0.30.9
- ChromaDB:  1.5.9
