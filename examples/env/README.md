# Example settings

Each file holds the lines to put in `.env` for one kind of computer. The rest of `.env` comes from `.env.example`, and `./install.sh` creates it for you.

| File | For | Same as running |
|---|---|---|
| `all-local.env` | NVIDIA GPUs with about 23 GB in total, such as 2 × 12 GB or 1 × 24 GB | `./install.sh --local` |
| `hearing-in-cloud.env` | one 16 GB card, or 8 GB with 32 GB of RAM | `./install.sh --cloud hearing --key KEY` |
| `brain-and-hearing-in-cloud.env` | one 12 GB card with 16 GB of RAM | `./install.sh --cloud brain,hearing --key KEY` |
| `all-cloud.env` | any computer, no GPU needed | `./install.sh --cloud all --key KEY` |

Using the installer is easier, because it also sets the GPU layout and downloads only what the local parts need. To change a setting by hand, copy the lines into `.env`, then run `./install.sh` again so it installs anything newly needed. See `docs/CLOUD.md` for what each cloud part costs.
