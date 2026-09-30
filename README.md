# ubuntu-scr-saver

A modern Ubuntu screensaver with a balanced clock, a balanced two-line English
reflection, and a compact live resource dashboard. Built with Vite 8.3.1, TypeScript 7.0.2, and a Python standard-library
resource server.

## Stack actually used

Verified against the npm registry on 2026-09-30:

| Component | Installed version | Role |
| --- | --- | --- |
| Vite | 8.3.1, latest stable | Builds the production HTML, CSS, and JavaScript |
| TypeScript | 7.0.2, latest stable | All frontend behavior is implemented in typed modules |
| Node.js | 24.21.0 | Runs the build tools locally |
| Python | 3.14.4 | Runs the Linux resource API, idle monitor, and launcher |

`npm run build` runs the TypeScript check and Vite build. The Python service
serves the resulting assets from `dist/`; `index.html` imports `src/main.ts`,
which connects the clock, quote rotation, and resource dashboard modules.
The exact dependency versions are pinned in `package.json` and `package-lock.json`.
Versions are fixed for reproducibility; rerun `npm view vite version` and
`npm view typescript version` before updating them in the future.

![Screensaver preview](docs/preview.png)

A moderately sized clock occupies the upper area, with a larger two-line
English reflection in the center. The lower monitoring panel groups four resource
cells in one row, switching to a two-by-two grid on narrower displays. The dark layout uses
restrained accents and generous margins.

## Install

Requires Ubuntu GNOME, Python 3.10+, Google Chrome, and a Node.js version
supported by Vite (20.19+ or 22.12+).

```bash
git clone https://github.com/savvy773/ubuntu-scr-saver.git
cd ubuntu-scr-saver
./install.sh
```

The installer builds the frontend, adds a **scr-saver** desktop shortcut and
application entry, and enables `screensaver.service`. The service opens the
screensaver after 30 minutes of inactivity. Click the desktop icon to open it
at any time; press a key to exit. The mouse pointer stays visible; mouse movement,
clicks, and touch do not close the screensaver.

The local installation is `/home/suby/code/scr-saver`. The installer records
the current project path so it also works when cloned into another folder.
After moving an installed folder, run `./install.sh` again to update paths.

## Features

- CPU utilization, RAM usage, system disk `/`, and the 1 TB HDD at `/mnt/data`.
- Used and remaining capacity in GiB, on separate colored rows below each percentage.
- Used capacity is warm peach; remaining capacity is sky blue, with larger numerals.
- RAM remaining uses MemAvailable; disk remaining uses actual available space from the filesystem.
- Total capacity is available in the capacity tooltip.
- One wide, high-contrast vertical usage gauge per resource, with quarter-scale marks.
- Readings update smoothly without clearing the previous values. Fixed readout
  columns, tabular digits, and fixed status badges prevent layout shifts when
  readings gain a digit or cross a warning threshold.
- Larger colored CPU, RAM, SSD, and HDD labels sit at the top, beside a compact status badge.
- A unified monitoring panel uses four aligned cells with subtle dividers and
  10-pixel spacing between resource sections.
- Percentages and gauges form a centered group with a 40-pixel gap.
- Distinct processor, memory, solid-state drive, and hard-drive icons identify the resources. Used and remaining capacity sit directly below each percentage.
- Both percentages and gauges use green for normal usage, amber for watch, and
  red for high usage; status labels accompany the colors.
- Watch/high defaults: CPU 60/85%, RAM 75/90%, both disks 80/90%.
- Resource readings refresh three seconds after each completed request.
- Memory usage excludes available memory; disk percentages match `df`.
- A disconnected HDD shows as unavailable instead of reporting the root disk.
- Rounded Nunito clock with larger date and weekday text, seconds, and AM/PM; fixed position.
- A centered two-line English reflection with larger adaptive text, randomly
  rotated every ten minutes.
- 120 shorter original passages, shuffled without repeats within each cycle.
- Subtle pastel highlights for auxiliary verbs, main verbs, conjunctions, and prepositions.
- Responsive clock and resource card layout.
- Visible mouse pointer and keyboard-only exit.

The active compact library is `src/compact-quote-library.ts`; the earlier long
reflections remain in `src/quote-library.ts` for later use. The quote sequence
and rotation deadline persist across launches. Reflections
use balanced word-boundary breaks and adaptive sizing to stay on two lines; very narrow displays truncate overflow
with an ellipsis and retain the full passage in the tooltip.

Resource readings work locally. Google Fonts load when available; system fonts
provide an offline fallback.

## Manual cache maintenance

Open **캐시 관리** in the monitoring panel, choose RAM, SSD, or HDD, and
preview the targets. Cleanup runs only after checking the confirmation box
and clicking the execution button. It never runs automatically. Keyboard
input inside this dialog does not exit the screensaver; Escape closes the dialog.

- **SSD:** Only thumbnail, fontconfig, Mesa shader, and Chrome cache folders
  under the user's cache directory are eligible. The entire `~/.cache` directory
  is never selected. Choose files older than 7 days, 30 days, or all ages.
- **HDD:** Enter an existing thumbnail, fontconfig, Mesa shader, or Chrome cache
  folder under `/mnt/data`. The HDD must be mounted. Arbitrary `cache` and `tmp`
  folders, its root, and other filesystems are excluded; the path is remembered locally.
- **Dependency protection:** uv, pnpm, npm, Yarn, pip, Poetry, Conda, Bun,
  virtual environments, installed dependency folders, Git, and Codex runtimes
  are excluded. Folders containing package manifests, lockfiles, or Python
  environment markers are skipped, including within eligible caches.
- **RAM:** Manually releases clean Linux file-read and metadata caches using
  `vm.drop_caches=3`; it does not close applications. Administrator permission
  is required through noninteractive sudo. Linux normally reclaims these caches
  itself, and rebuilding them may make subsequent reads slower; see the
  [kernel drop_caches documentation](https://www.kernel.org/doc/html/latest/admin-guide/sysctl/vm.html#drop-caches).

After cleanup the dashboard refreshes immediately. RAM cleanup reports cache
size before and after; the RAM usage figure already excludes reclaimable memory,
so clearing a read cache may produce little change in the displayed percentage.
The cache button, status area, dialog frame, and clock position stay fixed.

Disk previews expire after ten minutes. Symlinks are excluded, files changed
since preview are skipped, and directories are retained. The displayed disk
size is the sum of file sizes; actual recovered space can differ for open files
or shared filesystem blocks.

## Commands

```bash
python3 screensaver.py --now         # Open immediately
python3 screensaver.py --timer 10m   # Open in ten minutes
python3 screensaver.py --daemon --idle 1800

systemctl --user status screensaver.service
systemctl --user restart screensaver.service
```

The API and built frontend are served only on `127.0.0.1:8767`. Resource
readings are available at `/api/resources`. Files are served from `dist/`.

## Development

```bash
npm ci
npm run dev     # Vite with a proxy to the running resource service
npm run build   # Type check and build production assets
python3 -m unittest discover -s tests  # Dependency protection using temporary files
```

After building, an open screen reloads automatically within the resource refresh
interval. Restart the service when changing the Python backend.

- `src/`: TypeScript and CSS.
- `index.html`: Frontend entry point.
- `screensaver.py`: Idle monitor, launcher, and resource API.
- `maintenance.py`: Scoped cache previews and manual cleanup.
- `src/maintenance.ts`: Cache dialog and confirmation flow.
- `install.sh`: Builds and installs the desktop shortcut and service.
- `launch.sh`: Starts the resource service before opening the screensaver.
- `assets/`: Desktop icon.
- `dist/`, `node_modules/`, and local backups are excluded from Git.
