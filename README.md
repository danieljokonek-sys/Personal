# Claude Bots

Central hub for all Claude Code created programs and bots.

## Projects

| Folder | Name | Description |
|--------|------|-------------|
| `email-tracker/` | **Email Tracker** | Monitors 3 Gmail accounts, analyzes emails with Claude, tracks deadlines, agreements, action items, and Chorus Crafters song orders. Sends daily digest briefings. Reply to a digest with "done A3" to mark items complete. |

## Quick Start

Each project is self-contained. To run one:

```bash
cd email-tracker
pip install -r requirements.txt
python main.py run
```

Or use the included run scripts:

- **Windows:** Double-click `run.bat` inside the project folder
- **Mac/Linux:** Run `./run.sh` inside the project folder

## Adding New Bots

Create a new folder at the root level with a simple, descriptive name:

```
Claude Bots/
├── email-tracker/
├── your-new-bot/
└── another-project/
```

Each folder should be self-contained with its own `requirements.txt`, config, and run scripts.
