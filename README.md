# EbInventory Manager

EbInventory Manager is a desktop inventory-grid application built with Python and Tkinter. Create custom-shaped items, place them on a configurable grid, rotate and move them, and save the inventory for the next session.

## Requirements

- Python 3.9 or newer
- Tkinter
  - Tkinter is normally included with the official Python installer on Windows.
  - On Debian or Ubuntu, install it with `sudo apt install python3-tk` if it is missing.
- No third-party Python packages are required to run the source code.

## Installation

1. Clone or download the project.
2. Open PowerShell in the project directory:

   ```powershell
   cd path\to\EbinventoryManager
   ```

3. Optional but recommended: create and activate a virtual environment:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, run the script directly instead:

   ```powershell
   .\venv\Scripts\python.exe EbinventoryManager.py
   ```

## Running From Source

With Python available, start the application with:

```powershell
py EbinventoryManager.py
```

If a virtual environment is active, you can use:

```powershell
python EbinventoryManager.py
```

The application opens a window with an item sidebar and an inventory grid.

## How It Works

### Create an item

1. Click `+` in the sidebar.
2. Choose the item width and height.
3. Click or drag across cells to draw the shape.
4. Enter a name and choose a color.
5. Click **Save Item**.

Empty rows and columns around the drawn shape are removed automatically.

### Place and rotate items

1. Drag an item from the sidebar onto the grid.
2. Move the pointer over a valid location. The preview is green when the item fits and red when it does not.
3. Release the mouse button to place it.
4. Press `A` to rotate counter-clockwise or `D` to rotate clockwise while dragging. Right-click while dragging rotates clockwise.

Each item template can be placed only once at a time.

### Manage placed items

- Drag a placed item to move it.
- Press `A`, `D`, or right-click while moving it to rotate it.
- Right-click a placed item to remove it.
- Hover over a placed item to see its name.

### Manage item templates

Right-click an item in the sidebar to:

- **Edit** its name, color, or shape.
- **Duplicate** it.
- **Delete** it and any placed copies.

You can also double-click an item to edit it.

### Configure the grid

Click **Settings** to change the number of rows and columns. The grid supports values from 1 to 30. Items that no longer fit after resizing are removed.

### Save and reset

- Click **Save inventory state** to save the current grid size and placements.
- If a saved inventory exists, it is loaded automatically at startup.
- Click **Clear inventory** to remove all placed items while keeping the item templates.
- Click **Guide** inside the application for a short built-in usage guide.

## Local Data Files

The application stores data next to the Python script or packaged executable:

- `custom_items.json` stores item templates, shapes, colors, and names.
- `inventory_state.json` stores the grid size and current item placements.

These files are local application data and are ignored by Git in this project. Copy them separately if you need to transfer a personal inventory to another installation.

## Build a Windows Executable

PyInstaller can package the application as a windowed executable. Install it in the active environment:

```powershell
python -m pip install pyinstaller
```

Build using the included specification file:

```powershell
pyinstaller "EbInventory Manager.spec"
```

The executable is created in `dist\EbInventory Manager\` or the corresponding PyInstaller output directory. The generated `build\` and `dist\` folders are ignored by Git.

You can also build directly without the spec file:

```powershell
pyinstaller --onefile --windowed --name "EbInventory Manager" EbinventoryManager.py
```

When using a packaged executable, keep `custom_items.json` and `inventory_state.json` in the same directory as the `.exe` so the application can load and save your data.

## Project Files

- `EbinventoryManager.py` - application source code.
- `EbInventory Manager.spec` - PyInstaller build configuration.
- `.gitignore` - generated-file and local-data ignore rules.
- `custom_items.json` - optional local item-template data.
- `inventory_state.json` - optional local saved inventory.
