import sys
import os
import json
import anthropic
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from getpass import getpass

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH        = os.path.join(os.path.expanduser("~"), "juniper_vector_db")
TOP_K          = 12     # number of chunks to keep after filtering
FETCH_K        = 24     # fetch more candidates before filtering/dedup
MAX_CONTEXT    = 12000  # chars of book context sent to Claude
MIN_RELEVANCE  = 1.2    # ChromaDB L2 distance ceiling
CLAUDE_MODEL   = "claude-sonnet-4-6"
NETCONF_PORT   = 830
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

# ── API key check ─────────────────────────────────────────────────────────────
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("❌ ANTHROPIC_API_KEY is not set.")
    print("   Add it to ~/.bashrc:  export ANTHROPIC_API_KEY='sk-ant-...'")
    sys.exit(1)

# ── Args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 3:
    print("Usage: python do_configure.py <device-ip> 'what you want to do'")
    print("")
    print("Examples:")
    print("  python do_configure.py 192.168.1.1 'harden this switch'")
    print("  python do_configure.py 192.168.1.1 'configure OSPF on all uplink interfaces'")
    print("  python do_configure.py 192.168.1.1 'set up NTP with authentication'")
    sys.exit(1)

device_ip = sys.argv[1]
task      = " ".join(sys.argv[2:])

# ── PyEZ import check ─────────────────────────────────────────────────────────
try:
    from jnpr.junos import Device
    from jnpr.junos.utils.config import Config
    from jnpr.junos.exception import ConnectError, CommitError, ConfigLoadError
except ImportError:
    print("❌ PyEZ not installed. Run:")
    print("   ./juniper-env/bin/pip install junos-eznc")
    sys.exit(1)

# ── Credentials ───────────────────────────────────────────────────────────────
print("")
print("=" * 60)
print(f" Juniper AI Configurator")
print(f" Device : {device_ip}")
print(f" Task   : {task}")
print("=" * 60)
print("")

username = input("Username: ").strip()
password = getpass("Password: ")

# ── Connect to device ─────────────────────────────────────────────────────────
print(f"\n🔌 Connecting to {device_ip} via NETCONF...")

try:
    dev = Device(
        host=device_ip,
        user=username,
        password=password,
        port=NETCONF_PORT
    )
    dev.open()
    print(f"✅ Connected. Model: {dev.facts.get('model', 'unknown')}  "
          f"Junos: {dev.facts.get('version', 'unknown')}")
except ConnectError as e:
    print(f"❌ Could not connect to {device_ip}: {e}")
    print("   Check the IP, credentials, and that NETCONF is enabled:")
    print("   set system services netconf ssh")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected connection error: {e}")
    sys.exit(1)

# ── Pull current config ───────────────────────────────────────────────────────
print("\n📥 Pulling current device configuration...")

try:
    cu = Config(dev)
    current_config = dev.rpc.get_config(options={"format": "set"})
    config_text = current_config.text
    if not config_text:
        current_config = dev.rpc.get_config()
        config_text = str(current_config.tostring(pretty_print=True).decode())
    print(f"✅ Retrieved config ({len(config_text)} characters)")
except Exception as e:
    print(f"❌ Failed to retrieve config: {e}")
    dev.close()
    sys.exit(1)

MAX_CONFIG_CHARS = 8000
if len(config_text) > MAX_CONFIG_CHARS:
    config_text = config_text[:MAX_CONFIG_CHARS]
    print(f"⚠️  Config truncated to {MAX_CONFIG_CHARS} chars to fit context window.")

# ── RAG: find relevant book chunks ───────────────────────────────────────────
print(f"\n🔍 Searching knowledge base for: {task}")

ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    url="http://localhost:11434/api/embeddings",
    model_name="all-minilm"
)

try:
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    collection = chroma_client.get_collection(
        name="juniper_books",
        embedding_function=ollama_ef
    )
except Exception as e:
    print(f"❌ Could not open vector database: {e}")
    dev.close()
    sys.exit(1)

try:
    results = collection.query(
        query_texts=[task],
        n_results=FETCH_K,
        include=["documents", "metadatas", "distances"]
    )
except Exception as e:
    print(f"❌ Search failed: {e}")
    dev.close()
    sys.exit(1)

docs      = results["documents"][0]
metas     = results["metadatas"][0]
distances = results["distances"][0]

seen_pages = set()
relevant = []

for doc, meta, dist in zip(docs, metas, distances):
    if dist > MIN_RELEVANCE:
        continue
    key = (meta.get("source", "unknown"), meta.get("page", "?"))
    if key in seen_pages:
        continue
    seen_pages.add(key)
    relevant.append((doc, meta, dist))
    if len(relevant) >= TOP_K:
        break

if not relevant:
    print(f"❌ No relevant content found for: {task}")
    print(f"   Try rephrasing or raise MIN_RELEVANCE above {MIN_RELEVANCE}")
    dev.close()
    sys.exit(1)

context_parts = []
sources = {}
char_count = 0

for doc, meta, dist in relevant:
    src  = meta.get("source", "unknown")
    page = meta.get("page", "?")
    snippet = f"[{src}, p.{page}]\n{doc}"
    if char_count + len(snippet) > MAX_CONTEXT:
        break
    context_parts.append(snippet)
    char_count += len(snippet)
    if src not in sources:
        sources[src] = set()
    sources[src].add(page)

context = "\n\n---\n\n".join(context_parts)
print(f"✅ Found {len(relevant)} relevant chunk(s) from {len(sources)} source(s)")

# ── Shared cached content blocks ──────────────────────────────────────────────
# These are identical across all three Claude calls so we define them once.
# Cache strategy:
#   - book context: same for both passes, cache it (breakpoint 1)
#   - device config: same for both passes, cache it (breakpoint 2)
#   - task / question: always dynamic, never cached

cached_book_context = {
    "type": "text",
    "text": f"Reference material from Juniper Day One books:\n\n{context}",
    "cache_control": {"type": "ephemeral"}  # breakpoint 1
}

cached_device_config = {
    "type": "text",
    "text": f"Current device configuration:\n\n{config_text}",
    "cache_control": {"type": "ephemeral"}  # breakpoint 2
}

client = anthropic.Anthropic()

# ── Pass 1: Ask Claude what values it needs ───────────────────────────────────
print(f"\n🤖 Analysing task requirements...")

gather_system = (
    "You are an expert Juniper network engineer.\n"
    "You will be given a device config, reference material, and a task.\n"
    "Your job is to identify what site-specific values are needed to complete the task.\n\n"
    "Site-specific values are things like: IP addresses, NTP server IPs, syslog server IPs,\n"
    "SNMP community strings, authentication keys, management subnets, VLAN IDs, AS numbers,\n"
    "interface names, BGP neighbor IPs, passwords, or any other value unique to this network.\n\n"
    "Do NOT ask for values that are already present in the current device config.\n"
    "Do NOT ask for values that have sensible defaults (e.g. SSH protocol version).\n"
    "Only ask for values that are genuinely required and unknown.\n\n"
    "Output a JSON array of objects. Each object must have:\n"
    "  - key: a short identifier (e.g. ntp_server, mgmt_subnet)\n"
    "  - question: the question to ask the user\n"
    "  - required: true or false\n"
    "  - example: an example value\n\n"
    "If no values are needed, output an empty array: []\n"
    "Output ONLY the JSON array, no explanation, no markdown."
)

try:
    gather_response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": gather_system,
                "cache_control": {"type": "ephemeral"}  # cache gather system prompt
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    cached_book_context,
                    cached_device_config,
                    {
                        "type": "text",
                        "text": f"Task: {task}\n\nWhat site-specific values are needed to complete this task?"
                    }
                ]
            }
        ],
        temperature=0
    )
    gather_raw = gather_response.content[0].text.strip()

    usage = gather_response.usage
    if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
        print(f"💾 Cache hit: {usage.cache_read_input_tokens} tokens read from cache")
    elif hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens:
        print(f"💾 Cache written: {usage.cache_creation_input_tokens} tokens cached for next run")

except Exception as e:
    print(f"❌ Claude API error: {e}")
    dev.close()
    sys.exit(1)

# Parse the JSON list of required values
try:
    clean = gather_raw.replace("```json", "").replace("```", "").strip()
    required_values = json.loads(clean)
except Exception:
    required_values = []

# ── Interactive value collection ──────────────────────────────────────────────
collected = {}

if required_values:
    print("")
    print("=" * 60)
    print(" I NEED A FEW VALUES TO COMPLETE THIS TASK")
    print(" Leave blank to skip optional items.")
    print("=" * 60)
    print("")

    for item in required_values:
        key      = item.get("key", "value")
        question = item.get("question", key)
        required = item.get("required", False)
        example  = item.get("example", "")

        label = f"  {question}"
        if example:
            label += f" (e.g. {example})"
        if not required:
            label += " [optional]"
        label += ": "

        is_secret = any(w in key.lower() for w in ["password", "key", "secret", "community"])
        if is_secret:
            value = getpass(label)
        else:
            value = input(label).strip()

        if value:
            collected[key] = value

    print("")

values_block = ""
if collected:
    values_block = "\n\nSite-specific values provided by the operator:\n"
    for k, v in collected.items():
        values_block += f"  {k}: {v}\n"

# ── Pass 2: Generate the actual configuration ─────────────────────────────────
print(f"🤖 Generating configuration...")

config_system = (
    "You are an expert Juniper network engineer. You will be given:\n"
    "1. Reference snippets from Juniper Day One books\n"
    "2. The current running configuration of a Junos device in set format\n"
    "3. A task to perform\n"
    "4. Site-specific values provided by the operator\n\n"
    "Your job is to generate ONLY the set and delete commands needed to complete the task.\n\n"
    "RULES:\n"
    "1. Analyse the current config first. Do NOT generate commands for things already correctly configured.\n"
    "2. Output ONLY set or delete commands, one per line, no explanations, no headers.\n"
    "3. Use exact Junos set command syntax.\n"
    "4. To disable or remove something always use 'delete', never 'set X disable'.\n"
    "5. Use the operator-provided values where needed. "
    "If a required value was not provided, skip those commands entirely.\n"
    "6. Be comprehensive — generate all commands needed to fully complete the task.\n"
    "7. If assigning a static IP to me0, always include 'delete interfaces me0 unit 0 family inet dhcp' first.\n"
    "8. Never use a network address (e.g. 192.168.10.0/24) as a host address — use the actual device IP.\n"
    "   If the operator provided a subnet but not a specific host IP, skip the static IP assignment.\n"
    "9. If the task cannot be completed safely, output only: CANNOT_COMPLETE: <reason>\n"
    "10. Do not output anything except set/delete commands or CANNOT_COMPLETE."
)

try:
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": config_system,
                "cache_control": {"type": "ephemeral"}  # cache config system prompt
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    cached_book_context,   # cache hit if within 5 min TTL
                    cached_device_config,  # cache hit if within 5 min TTL
                    {
                        "type": "text",
                        "text": f"Task: {task}{values_block}\n\nOutput only the set/delete commands needed:"
                    }
                ]
            }
        ],
        temperature=0
    )
    raw_output = message.content[0].text.strip()

    usage = message.usage
    if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
        print(f"💾 Cache hit: {usage.cache_read_input_tokens} tokens read from cache")
    elif hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens:
        print(f"💾 Cache written: {usage.cache_creation_input_tokens} tokens cached for next run")

except anthropic.AuthenticationError:
    print("❌ Invalid API key.")
    dev.close()
    sys.exit(1)
except Exception as e:
    print(f"❌ Claude API error: {e}")
    dev.close()
    sys.exit(1)

# ── Check for CANNOT_COMPLETE ─────────────────────────────────────────────────
if raw_output.startswith("CANNOT_COMPLETE"):
    print(f"\n⚠️  Claude cannot complete this task:")
    print(f"   {raw_output.replace('CANNOT_COMPLETE: ', '')}")
    dev.close()
    sys.exit(0)

# Parse commands — only lines starting with set or delete
raw_commands = [
    line.strip()
    for line in raw_output.splitlines()
    if line.strip().startswith(("set ", "delete "))
]

if not raw_commands:
    print("\n⚠️  Claude did not generate any valid set/delete commands.")
    print("   Raw output:")
    print(raw_output)
    dev.close()
    sys.exit(0)

# ── Sanitise commands ─────────────────────────────────────────────────────────
INVALID_COMMANDS = [
    "set chassis aggregated-devices ethernet device-count 0",
    "set system ddos-protection global bandwidth-scale",
    "set system ddos-protection global burst-scale",
]

INCOMPLETE_PREFIXES = [
    "set system ntp authentication-key",
]

PLACEHOLDERS = ["$9$\"\"", "$9$", "<value>", "<password>", "<key>", "YOUR_", "REPLACE", "CHANGE_THIS"]

commands = []
warnings = []

for cmd in raw_commands:
    if "CANNOT_COMPLETE" in cmd:
        warnings.append(f"  ⚠️  Skipped (Claude could not complete): '{cmd}'")
        continue

    if any(cmd.startswith(invalid) or cmd == invalid for invalid in INVALID_COMMANDS):
        warnings.append(f"  ⚠️  Skipped (invalid command): '{cmd}'")
        continue

    if any(cmd.startswith(prefix) for prefix in INCOMPLETE_PREFIXES):
        warnings.append(f"  ⚠️  Skipped (incomplete — requires manual value): '{cmd}'")
        warnings.append(f"       Configure NTP authentication manually with a real key value.")
        continue

    if cmd.startswith("set ") and cmd.endswith(" disable"):
        fixed = "delete " + cmd[4:-8].strip()
        warnings.append(f"  ⚠️  Fixed: '{cmd}'")
        warnings.append(f"       → '{fixed}'")
        commands.append(fixed)
        continue

    if any(p in cmd for p in PLACEHOLDERS):
        warnings.append(f"  ⚠️  Skipped (placeholder value): '{cmd}'")
        warnings.append(f"       Replace the placeholder with a real value and apply manually.")
        continue

    commands.append(cmd)

# ── Order commands ────────────────────────────────────────────────────────────
# Junos commit check validates references at apply time, so dependent objects
# must be defined before they are referenced. Sort into safe apply order:
#   1. delete commands first (clear conflicts)
#   2. system/routing/protocols/snmp/firewall definitions
#   3. interface commands last (may reference firewall filters)

def command_order(cmd):
    if cmd.startswith("delete"):
        return 0
    if cmd.startswith("set system"):
        return 1
    if cmd.startswith("set routing-options"):
        return 2
    if cmd.startswith("set protocols"):
        return 3
    if cmd.startswith("set snmp"):
        return 4
    if cmd.startswith("set firewall"):
        return 5
    if cmd.startswith("set interfaces"):
        return 6
    if cmd.startswith("set chassis"):
        return 7
    return 8

commands.sort(key=command_order)


print("")
print("=" * 60)
print(" PROPOSED CONFIGURATION CHANGES")
print("=" * 60)
for cmd in commands:
    print(f"  {cmd}")
print("=" * 60)
print(f" {len(commands)} command(s) | Sources: {', '.join(sources.keys())}")
print("=" * 60)

if warnings:
    print("")
    print("=" * 60)
    print(" WARNINGS (review before proceeding)")
    print("=" * 60)
    for w in warnings:
        print(w)
    print("=" * 60)

if not commands:
    print("\n⚠️  No valid commands remain after sanitisation.")
    print("   Review the warnings above and apply manually if needed.")
    dev.close()
    sys.exit(0)

# ── Dry run / commit check ────────────────────────────────────────────────────
print("\n🔍 Running commit check (dry run)...")

try:
    cu.lock()
    config_block = "\n".join(commands)
    cu.load(config_block, format="set")
    check_result = cu.commit_check()
    if check_result:
        print("✅ Commit check passed — configuration is valid.")
    else:
        print("❌ Commit check failed — configuration has errors.")
        cu.rollback()
        cu.unlock()
        dev.close()
        sys.exit(1)
except ConfigLoadError as e:
    print(f"❌ Config load error: {e}")
    try:
        cu.rollback()
        cu.unlock()
    except Exception:
        pass
    dev.close()
    sys.exit(1)
except Exception as e:
    print(f"❌ Dry run error: {e}")
    try:
        cu.rollback()
        cu.unlock()
    except Exception:
        pass
    dev.close()
    sys.exit(1)

# ── Confirm and apply ─────────────────────────────────────────────────────────
print("")
confirm = input("Apply this configuration? (yes/no): ").strip().lower()

if confirm != "yes":
    print("\n⚠️  Aborted. Rolling back...")
    cu.rollback()
    cu.unlock()
    dev.close()
    print("✅ No changes were made.")
    sys.exit(0)

print("\n📤 Applying configuration...")

try:
    cu.commit(comment=f"AI configurator: {task}")
    cu.unlock()
    print("✅ Configuration committed successfully.")
except CommitError as e:
    print(f"❌ Commit failed: {e}")
    print("   Rolling back...")
    cu.rollback()
    cu.unlock()
    dev.close()
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error during commit: {e}")
    try:
        cu.rollback()
        cu.unlock()
    except Exception:
        pass
    dev.close()
    sys.exit(1)

# ── Done ──────────────────────────────────────────────────────────────────────
dev.close()

print("")
print("=" * 60)
print(" DONE")
print("=" * 60)
print(f" Task   : {task}")
print(f" Device : {device_ip}")
print(f" Changes: {len(commands)} command(s) applied")
print("=" * 60)
