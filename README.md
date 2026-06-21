# Juniper Day One - Ask Books

A local system for querying Juniper Day One books using natural language. Ask questions about Junos OS configuration and get answers with actual CLI commands and config examples pulled directly from the books.

Includes an experimental AI configurator that can read a live device config, ask you for site-specific values, and apply changes based on the books. See do_configure.py below.

---

## How It Works

1. PDF books are chunked and embedded into a local ChromaDB vector database using
   the all-minilm embedding model running in Ollama.

2. When you ask a question, the query is embedded and used to find the most
   semantically relevant chunks from the books.

3. The relevant chunks are passed as context to Claude (claude-sonnet-4-6) via the
   Anthropic API, which generates a focused answer with actual Junos CLI commands.

Embeddings and retrieval run locally. Answer generation requires an internet connection
to reach the Anthropic API. Your PDF content is sent to Anthropic only as part of the
query context.

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
Costs are minimal for this use case (approximately $0.01 per query depending on model used).

---

## Setup

Place your Juniper Day One PDF books in /srv/ftp/dayone, then run:

    chmod +x setup.sh
    ./setup.sh

This will:
- Create a Python virtual environment
- Install all dependencies including the Anthropic SDK
- Pull the all-minilm embedding model via Ollama
- Index all PDFs into the ChromaDB vector database

Indexing 30 books takes approximately 10 to 20 minutes. Progress is saved after
each book so if the process is interrupted it will resume where it left off.

---

## Usage: ask_books.py

Ask any question about Junos OS in plain English.

    python3 ask_books.py "your question here"

Examples:

    python3 ask_books.py "how do I configure a BGP neighbor?"
    python3 ask_books.py "show me OSPF area configuration on Junos"
    python3 ask_books.py "how do I configure EVPN VXLAN on an EX switch?"
    python3 ask_books.py "what is the Junos command to check BGP neighbor state?"

Example output:

    $ python3 ask_books.py "show me a complete EBGP configuration with authentication and route policy on Junos"
    ============================================================
    ANSWER:
    ============================================================
    Here is the complete EBGP configuration with authentication and route policy:

    set protocols bgp group EBGP type external
    set protocols bgp group EBGP peer-as 65001
    set protocols bgp group EBGP neighbor 10.0.0.1
    set protocols bgp group EBGP authentication key "my_secret_key"
    set protocols bgp group EBGP authentication algorithm md5
    set policy-options policy-statement send-direct term 1 from protocol direct
    set policy-options policy-statement send-direct term 1 then accept

    Explanation:

    set protocols bgp group EBGP type external
      Sets up an External BGP peer group called EBGP. The type external keyword
      specifies this is an EBGP peer, as opposed to an IBGP peer.

    set protocols bgp group EBGP peer-as 65001
      Sets the Autonomous System Number for the EBGP peer group. Replace with
      your actual peer ASN.

    set protocols bgp group EBGP neighbor 10.0.0.1
      Specifies the IP address of the neighboring router. Replace with the actual
      IP address of your BGP neighbor.

    set protocols bgp group EBGP authentication key "my_secret_key"
      Sets the authentication key for the peer group. Replace with a strong,
      unique password that meets your organization's security policy.

    set protocols bgp group EBGP authentication algorithm md5
      Specifies MD5 as the authentication algorithm for the peer group.

    set policy-options policy-statement send-direct term 1 from protocol direct
      Creates a policy statement called send-direct that matches routes learned
      directly (not through an intermediate router).

    set policy-options policy-statement send-direct term 1 then accept
      Accepts routes that match the criteria in the previous line.

    ============================================================
    SOURCES:
      EX_Series_UpRunning.pdf — p.177
      junos-beginners-guide.pdf — p.9
      ExploreJunosCLI_2ndEd.pdf — p.80
      TW_HardeningJunosDevices_2ndEd.pdf — p.96, p.151
      TW_HardeningJunosDevices_2ndEd_Checklist.pdf — p.1
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

Requires PyEZ and NETCONF enabled on the device:

    set system services netconf ssh

Install PyEZ into the virtual environment:

    ./juniper-env/bin/pip install junos-eznc

Run it:

    ./juniper-env/bin/python do_configure.py <device-ip> "what you want to do"

Examples:

    ./juniper-env/bin/python do_configure.py 192.168.1.1 "harden this switch"
    ./juniper-env/bin/python do_configure.py 192.168.1.1 "configure OSPF on all uplink interfaces"
    ./juniper-env/bin/python do_configure.py 192.168.1.1 "set up NTP with authentication"
    ./juniper-env/bin/python do_configure.py 192.168.1.1 "disable unused services and secure SSH"

Example session:

    $ ./juniper-env/bin/python do_configure.py 192.168.1.1 "harden this switch"
    ============================================================
     Juniper AI Configurator
     Device : 192.168.1.1
     Task   : harden this switch
    ============================================================

    Username: admin
    Password:

    🔌 Connecting to 192.168.1.1 via NETCONF...
    ✅ Connected. Model: EX2300-C-12P  Junos: 23.2R2-S7.5

    📥 Pulling current device configuration...
    ✅ Retrieved config (4221 characters)

    🔍 Searching knowledge base for: harden this switch
    ✅ Found 6 relevant chunk(s) from 3 source(s)

    🤖 Analysing task requirements...

    ============================================================
     I NEED A FEW VALUES TO COMPLETE THIS TASK
     Leave blank to skip optional items.
    ============================================================

      What is the IP address of the TACACS+ server? (e.g. 192.168.1.10) [optional]: 192.168.10.1
      What is the TACACS+ shared secret key? (e.g. MyT@cacs$ecret123) [optional]:
      What is the primary NTP server IP address or hostname? (e.g. 192.168.1.20): 1.1.1.1
      What is the secondary NTP server IP address (if any)? (e.g. 192.168.1.21) [optional]: 2.2.2.2
      What is the IP address of the remote syslog server? (e.g. 192.168.1.30) [optional]: 192.168.10.30
      What is the management subnet permitted to access this device? (e.g. 10.0.0.0/24): 192.168.10.0/24
      What login banner should be displayed at login? [optional]: Authorized access only.

    🤖 Generating configuration...

    ============================================================
     PROPOSED CONFIGURATION CHANGES
    ============================================================
      delete interfaces me0 unit 0 family inet dhcp
      set interfaces me0 unit 0 family inet address 192.168.10.203/24
      set routing-options static route 0.0.0.0/0 next-hop 192.168.10.1
      set system login message "Authorized access only."
      set system services ssh root-login deny
      set system services ssh protocol-version v2
      set system services ssh connection-limit 5
      set system services ssh rate-limit 5
      delete system services xnm-clear-text
      set system tacplus-server 192.168.10.1 secret <secret>
      set system authentication-order [ tacplus password ]
      set system ntp server 1.1.1.1
      set system ntp server 2.2.2.2
      set system syslog host 192.168.10.30 any any
      set system syslog host 192.168.10.30 port 514
      set firewall family inet filter PROTECT-RE term ALLOW-MGMT from source-address 192.168.10.0/24
      set firewall family inet filter PROTECT-RE term ALLOW-MGMT from destination-port ssh
      set firewall family inet filter PROTECT-RE term ALLOW-MGMT then accept
      set firewall family inet filter PROTECT-RE term ALLOW-NETCONF from source-address 192.168.10.0/24
      set firewall family inet filter PROTECT-RE term ALLOW-NETCONF from destination-port 830
      set firewall family inet filter PROTECT-RE term ALLOW-NETCONF then accept
      set firewall family inet filter PROTECT-RE term ALLOW-NTP from source-address 1.1.1.1/32
      set firewall family inet filter PROTECT-RE term ALLOW-NTP from source-address 2.2.2.2/32
      set firewall family inet filter PROTECT-RE term ALLOW-NTP from destination-port ntp
      set firewall family inet filter PROTECT-RE term ALLOW-NTP then accept
      set firewall family inet filter PROTECT-RE term ALLOW-ICMP from protocol icmp
      set firewall family inet filter PROTECT-RE term ALLOW-ICMP then accept
      set firewall family inet filter PROTECT-RE term DENY-ALL then discard
      set interfaces me0 unit 0 family inet filter input PROTECT-RE
    ============================================================
     29 command(s) | Sources: TW_HardeningJunosDevices_2ndEd.pdf, DO_ConfiguringEX_3rdEd.pdf
    ============================================================

    🔍 Running commit check (dry run)...
    ✅ Commit check passed — configuration is valid.

    Apply this configuration? (yes/no): yes

    📤 Applying configuration...
    ✅ Configuration committed successfully.

    ============================================================
     DONE
    ============================================================
     Task   : harden this switch
     Device : 192.168.1.1
     Changes: 29 command(s) applied
    ============================================================

Claude reads the current config before generating commands so it only produces
changes for things not already configured. The commit check validates the config
on the device before anything is applied, and the script rolls back automatically
if the commit fails.

Always review the warnings section — some commands may be skipped if values were
not provided or if the sanitiser detected invalid syntax. Apply those manually if
needed.

---

## File Structure

    juniper-ask-books/
    |-- ask_books.py              Query the vector database and generate answers
    |-- do_configure.py           AI configurator — reads device and applies changes
    |-- index_books.py            Index PDF books into ChromaDB
    |-- requirements.txt          Python dependencies
    |-- setup.sh                  Automated setup script
    |-- .gitignore                Excludes venv, database, and PDFs from git
    |-- README.md                 This file
    |-- juniper-env/              Python virtual environment (not committed)
    |-- juniper_vector_db/        ChromaDB vector database (not committed)
    |-- juniper_index_checkpoint.json  Indexing progress tracker (not committed)

---

## Re-indexing

To re-index from scratch (for example after adding new books):

    rm -rf juniper_vector_db juniper_index_checkpoint.json
    python3 index_books.py

Note: DB_PATH and CHECKPOINT_FILE in index_books.py default to your home directory.
If you are running as a different user, update those paths at the top of the script.

To add new books without re-indexing existing ones, just place the new PDFs in
/srv/ftp/dayone and re-run index_books.py. Already indexed books will be skipped.

---

## Configuration

Key settings are at the top of each script:

index_books.py:
- BOOK_DIR       Path to PDF books (default /srv/ftp/dayone)
- DB_PATH        Path to ChromaDB database
- CHUNK_SIZE     Characters per chunk (default 1200)
- CHUNK_STEP     Step between chunks, controls overlap (default 900)

ask_books.py:
- TOP_K          Number of chunks to keep after filtering (default 6)
- FETCH_K        Number of candidates to fetch before filtering (default 12)
- MAX_CONTEXT    Max characters of context sent to Claude (default 7000)
- MIN_RELEVANCE  L2 distance threshold, lower is stricter (default 1.2)
- CLAUDE_MODEL   Anthropic model to use (default claude-sonnet-4-6)

do_configure.py:
- TOP_K          Number of chunks to keep after filtering (default 6)
- FETCH_K        Number of candidates to fetch before filtering (default 12)
- MAX_CONTEXT    Max characters of book context sent to Claude (default 6000)
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
