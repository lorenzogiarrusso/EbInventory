from __future__ import annotations

import json
import random
import sys
import tkinter as tk
import uuid
from dataclasses import dataclass
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from typing import Optional


def get_storage_directory() -> Path:
	if getattr(sys, "frozen", False):
		return Path(sys.executable).resolve().parent
	return Path(__file__).resolve().parent


@dataclass(frozen=True)
class ItemTemplate:
	item_id: str
	name: str
	width: int
	height: int
	color: str
	mask: tuple[tuple[bool, ...], ...]


@dataclass
class Placement:
	template: ItemTemplate
	row: int
	col: int
	rotation: int = 0


class EbInventoryGridApp:
	FONT_FAMILY = "Segoe UI"

	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("EbInventory Manager")
		self.root.geometry("1100x720")
		self.root.minsize(900, 600)

		self.cell_size = 56
		self.grid_rows = 8
		self.grid_cols = 8

		storage_directory = get_storage_directory()
		self.storage_path = storage_directory / "custom_items.json"
		self.inventory_save_path = storage_directory / "inventory_state.json"
		self.templates = self._load_templates()
		self.item_available: dict[ItemTemplate, bool] = {template: True for template in self.templates}
		self.item_card_widgets: dict[ItemTemplate, dict[str, tk.Widget]] = {}
		self.items_frame: Optional[ttk.Frame] = None
		self.items_canvas: Optional[tk.Canvas] = None
		self.empty_sidebar_label: Optional[ttk.Label] = None

		self.placements: list[Placement] = []
		self.occupancy: list[list[Optional[Placement]]] = []
		self.cell_rectangles: dict[tuple[int, int], int] = {}

		self.dragging_template: Optional[ItemTemplate] = None
		self.drag_rotation: int = 0
		self.drag_preview: Optional[tuple[int, int, bool]] = None
		self.moving_placement: Optional[Placement] = None
		self.moving_rotation: int = 0
		self.move_preview: Optional[tuple[int, int, bool]] = None
		self.ghost_window: Optional[tk.Toplevel] = None
		self.ghost_canvas: Optional[tk.Canvas] = None
		self.hover_tooltip: Optional[tk.Toplevel] = None
		self.hover_label: Optional[tk.Label] = None

		self.status_var = tk.StringVar(value="Ready")
		self._load_inventory_state()

		self._build_styles()
		self._build_ui()
		self._rebuild_grid()

		self.root.bind_all("<KeyPress>", self._on_global_keypress)
		self.root.bind_all("<Motion>", self._on_global_motion)
		self.root.bind_all("<ButtonRelease-1>", self._on_global_release)

	def _build_styles(self) -> None:
		style = ttk.Style(self.root)
		try:
			style.theme_use("clam")
		except tk.TclError:
			pass

		style.configure("Sidebar.TFrame", background="#1f232a")
		style.configure("Main.TFrame", background="#f3f4f6")
		style.configure("Header.TLabel", background="#1f232a", foreground="white", font=(self.FONT_FAMILY, 16, "bold"))
		style.configure("Subtle.TLabel", background="#1f232a", foreground="#c8d0da", font=(self.FONT_FAMILY, 9))
		style.configure("Status.TLabel", background="#e5e7eb", foreground="#374151", font=(self.FONT_FAMILY, 9))
		style.configure("Action.TButton", font=(self.FONT_FAMILY, 10, "bold"), padding=(10, 6))

	def _build_ui(self) -> None:
		container = ttk.Frame(self.root)
		container.pack(fill="both", expand=True)

		self.sidebar = ttk.Frame(container, style="Sidebar.TFrame", width=280)
		self.sidebar.pack(side="left", fill="y")
		self.sidebar.pack_propagate(False)

		self.main = ttk.Frame(container, style="Main.TFrame")
		self.main.pack(side="right", fill="both", expand=True)

		self._build_sidebar()
		self._build_main_area()

		status_bar = ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w")
		status_bar.pack(side="bottom", fill="x")

	def _build_sidebar(self) -> None:
		header = ttk.Label(self.sidebar, text="Items", style="Header.TLabel")
		header.pack(anchor="w", padx=18, pady=(18, 6))

		subtitle = ttk.Label(
			self.sidebar,
			text="Drag items onto the grid. Rotate with A and D (or right-click) while dragging.",
			style="Subtle.TLabel",
			wraplength=230,
			justify="left",
		)
		subtitle.pack(anchor="w", padx=18, pady=(0, 18))

		create_button = tk.Button(
			self.sidebar,
			text="+",
			font=(self.FONT_FAMILY, 16, "bold"),
			bg="#2563eb",
			fg="white",
			activebackground="#1d4ed8",
			activeforeground="white",
			relief="flat",
			width=3,
			command=self._open_item_size_dialog,
		)
		create_button.pack(anchor="w", padx=18, pady=(0, 12))

		guide_button = tk.Button(
			self.sidebar,
			text="Guide",
			font=(self.FONT_FAMILY, 10, "bold"),
			bg="#374151",
			fg="white",
			activebackground="#4b5563",
			activeforeground="white",
			relief="flat",
			command=self._open_guide_dialog,
		)
		guide_button.pack(anchor="w", padx=18, pady=(0, 12))

		items_container = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
		items_container.pack(fill="both", expand=True)
		items_container.columnconfigure(0, weight=1)
		items_container.rowconfigure(0, weight=1)

		self.items_canvas = tk.Canvas(items_container, bg="#1f232a", highlightthickness=0)
		self.items_canvas.grid(row=0, column=0, sticky="nsew")
		items_scrollbar = ttk.Scrollbar(items_container, orient="vertical", command=self.items_canvas.yview)
		items_scrollbar.grid(row=0, column=1, sticky="ns")
		self.items_canvas.configure(yscrollcommand=items_scrollbar.set)

		self.items_frame = ttk.Frame(self.items_canvas, style="Sidebar.TFrame")
		items_window = self.items_canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
		self.items_frame.bind(
			"<Configure>",
			lambda _event: self.items_canvas.configure(scrollregion=self.items_canvas.bbox("all"))
		)
		self.items_canvas.bind(
			"<Configure>",
			lambda event: self.items_canvas.itemconfigure(items_window, width=event.width),
		)
		self.root.bind_all("<MouseWheel>", self._on_items_mousewheel)

		if not self.templates:
			self.empty_sidebar_label = ttk.Label(
				self.items_frame,
				text="No items yet. Use + to create one.",
				style="Subtle.TLabel",
				wraplength=230,
				justify="left",
			)
			self.empty_sidebar_label.pack(anchor="w", padx=18, pady=(0, 18))

		for template in self.templates:
			self._create_item_card(template)

		ttk.Separator(self.sidebar).pack(fill="x", padx=18, pady=18)
		ttk.Button(self.sidebar, text="Save inventory state", style="Action.TButton", command=self._save_inventory).pack(
			anchor="w", padx=18, pady=(0, 8)
		)

		ttk.Button(self.sidebar, text="Settings", style="Action.TButton", command=self._open_settings).pack(
			anchor="w", padx=18, pady=(0, 8)
		)
		ttk.Button(self.sidebar, text="Clear inventory", style="Action.TButton", command=self._clear_inventory).pack(
			anchor="w", padx=18
		)

	def _on_items_mousewheel(self, event: tk.Event) -> None:
		if self.items_canvas is None:
			return

		pointer_x, pointer_y = self.root.winfo_pointerxy()
		canvas_left = self.items_canvas.winfo_rootx()
		canvas_top = self.items_canvas.winfo_rooty()
		canvas_right = canvas_left + self.items_canvas.winfo_width()
		canvas_bottom = canvas_top + self.items_canvas.winfo_height()
		if not (canvas_left <= pointer_x < canvas_right and canvas_top <= pointer_y < canvas_bottom):
			return

		delta = event.delta
		steps = -int(delta / 120) if delta else 0
		if steps == 0 and delta:
			steps = -1 if delta > 0 else 1
		self.items_canvas.yview_scroll(steps, "units")

	def _open_guide_dialog(self) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title("Guide")
		dialog.resizable(False, False)
		dialog.transient(self.root)
		dialog.grab_set()

		frame = ttk.Frame(dialog, padding=18)
		frame.pack(fill="both", expand=True)

		title = ttk.Label(frame, text="How to use the EbInventory", font=(self.FONT_FAMILY, 14, "bold"))
		title.pack(anchor="w", pady=(0, 12))

		body = tk.Text(frame, width=58, height=16, wrap="word", borderwidth=0, highlightthickness=0)
		body.pack(fill="both", expand=True)
		body.configure(state="normal")
		body.insert(
			"1.0",
			(
				"Create an item:\n"
				"1. Click the + button.\n"
				"2. Choose the size.\n"
				"3. Draw the item shape in the grid.\n"
				"4. Give it a name and choose a color.\n\n"
				"Place an item:\n"
				"1. Drag it from the sidebar.\n"
				"2. Rotate it with A and D (or right-click) while dragging.\n"
				"3. Drop it on valid grid tiles.\n\n"
				"Remove an item:\n"
				"1. Right-click a placed item on the grid.\n\n"
				"Edit, duplicate or delete an item:\n"
				"1. Right-click the item in the sidebar.\n"
				"2. Choose Edit, Duplicate or Delete. To Edit, you can also just double-click on it.\n\n"
				"Save the inventory state:\n"
				"0. If a save already exists, it will be automatically loaded on startup.\n"
				"1. To save, click the Save inventory state button in the sidebar.\n"				
			)
		)
		body.configure(state="disabled")

		button_row = ttk.Frame(frame)
		button_row.pack(fill="x", pady=(12, 0))
		ttk.Button(button_row, text="Close", command=dialog.destroy).pack(side="right")

		dialog.update_idletasks()
		x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
		y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
		dialog.geometry(f"+{x}+{y}")

	def _create_item_card(self, template: ItemTemplate) -> None:
		parent = self.items_frame if self.items_frame is not None else self.sidebar
		card = tk.Frame(parent, bg="#2b313a", highlightbackground="#424956", highlightthickness=1, cursor="hand2")
		card.pack(fill="x", padx=18, pady=8)

		swatch = tk.Frame(card, width=18, height=18, bg=template.color, highlightthickness=0)
		swatch.pack(side="left", padx=12, pady=12)
		swatch.pack_propagate(False)

		text_frame = tk.Frame(card, bg="#2b313a")
		text_frame.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=10)

		name = tk.Label(
			text_frame,
			text=template.name,
			bg="#2b313a",
			fg="white",
			font=(self.FONT_FAMILY, 11, "bold"),
			anchor="w",
		)
		name.pack(fill="x")

		size = tk.Label(
			text_frame,
			text=f"{template.width} x {template.height}",
			bg="#2b313a",
			fg="#cbd5e1",
			font=(self.FONT_FAMILY, 9),
			anchor="w",
		)
		size.pack(fill="x", pady=(2, 0))

		for widget in (card, swatch, text_frame, name, size):
			widget.bind("<ButtonPress-1>", lambda event, item=template: self._begin_drag(item, event))
			widget.bind("<Double-Button-1>", lambda event, item=template: self._edit_template(item))
			widget.bind("<Button-3>", lambda event, item=template: self._show_item_context_menu(item, event))

		self.item_card_widgets[template] = {
			"card": card,
			"swatch": swatch,
			"text_frame": text_frame,
			"name": name,
			"size": size,
		}
		self._refresh_item_card(template)

	def _build_main_area(self) -> None:
		header_row = ttk.Frame(self.main, style="Main.TFrame")
		header_row.pack(fill="x", padx=18, pady=(18, 10))

		title = ttk.Label(header_row, text="Inventory Grid", font=(self.FONT_FAMILY, 18, "bold"), background="#f3f4f6")
		title.pack(side="left")

		grid_frame = ttk.Frame(self.main, style="Main.TFrame")
		grid_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

		self.grid_canvas = tk.Canvas(grid_frame, bg="#e5e7eb", highlightthickness=0)
		self.grid_canvas.grid(row=0, column=0, sticky="nsew")

		x_scroll = ttk.Scrollbar(grid_frame, orient="horizontal", command=self.grid_canvas.xview)
		y_scroll = ttk.Scrollbar(grid_frame, orient="vertical", command=self.grid_canvas.yview)

		self.grid_canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

		x_scroll.grid(row=1, column=0, sticky="ew")
		y_scroll.grid(row=0, column=1, sticky="ns")

		grid_frame.columnconfigure(0, weight=1)
		grid_frame.rowconfigure(0, weight=1)

		self.grid_canvas.bind("<Configure>", lambda _event: self._update_scroll_region())
		self.grid_canvas.bind("<ButtonPress-1>", self._on_grid_left_press)
		self.grid_canvas.bind("<B1-Motion>", self._on_grid_left_drag)
		self.grid_canvas.bind("<Motion>", self._on_grid_motion)
		self.grid_canvas.bind("<Leave>", self._on_grid_leave)
		self.grid_canvas.bind("<Button-3>", self._on_grid_right_click)

	def _open_settings(self) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title("Settings")
		dialog.resizable(False, False)
		dialog.transient(self.root)
		dialog.grab_set()

		frame = ttk.Frame(dialog, padding=18)
		frame.pack(fill="both", expand=True)

		ttk.Label(frame, text="Grid Settings", font=(self.FONT_FAMILY, 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

		ttk.Label(frame, text="Columns:").grid(row=1, column=0, sticky="w", pady=4)
		cols_var = tk.IntVar(value=self.grid_cols)
		cols_spin = tk.Spinbox(frame, from_=1, to=30, textvariable=cols_var, width=8)
		cols_spin.grid(row=1, column=1, sticky="w", pady=4)

		ttk.Label(frame, text="Rows:").grid(row=2, column=0, sticky="w", pady=4)
		rows_var = tk.IntVar(value=self.grid_rows)
		rows_spin = tk.Spinbox(frame, from_=1, to=30, textvariable=rows_var, width=8)
		rows_spin.grid(row=2, column=1, sticky="w", pady=4)

		note = ttk.Label(
			frame,
			text="Existing items are kept when possible. Items that no longer fit are removed.",
			wraplength=280,
			foreground="#6b7280",
		)
		note.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 14))

		button_row = ttk.Frame(frame)
		button_row.grid(row=4, column=0, columnspan=2, sticky="e")

		def apply_settings() -> None:
			try:
				new_cols = int(cols_var.get())
				new_rows = int(rows_var.get())
			except (tk.TclError, ValueError):
				messagebox.showerror("Invalid value", "Please enter valid whole numbers.")
				return

			new_cols = max(1, new_cols)
			new_rows = max(1, new_rows)

			self.grid_cols = new_cols
			self.grid_rows = new_rows
			removed = self._rebuild_grid()
			if removed:
				self._set_status(f"Grid resized to {new_cols} x {new_rows}. Removed {removed} item(s) that no longer fit.")
			else:
				self._set_status(f"Grid resized to {new_cols} x {new_rows}.")
			dialog.destroy()

		ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
		ttk.Button(button_row, text="Apply", command=apply_settings).pack(side="right")

		dialog.update_idletasks()
		x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
		y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
		dialog.geometry(f"+{x}+{y}")

	def _clear_inventory(self) -> None:
		for template in self.templates:
			self._set_item_available(template, True)
		self.placements.clear()
		self._rebuild_grid()
		self._set_status("Inventory cleared.")

	def _load_inventory_state(self) -> None:
		if not self.inventory_save_path.exists():
			return

		try:
			raw = json.loads(self.inventory_save_path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError):
			self._set_status("Could not load the saved inventory.")
			return

		if not isinstance(raw, dict):
			return

		stored_rows = raw.get("grid_rows")
		stored_cols = raw.get("grid_cols")
		if isinstance(stored_rows, int) and not isinstance(stored_rows, bool):
			self.grid_rows = min(30, max(1, stored_rows))
		if isinstance(stored_cols, int) and not isinstance(stored_cols, bool):
			self.grid_cols = min(30, max(1, stored_cols))

		templates_by_id = {template.item_id: template for template in self.templates}
		placements = raw.get("placements", [])
		if not isinstance(placements, list):
			return

		for entry in placements:
			if not isinstance(entry, dict):
				continue
			template = templates_by_id.get(str(entry.get("item_id", "")))
			if template is None:
				continue
			try:
				row = int(entry["row"])
				col = int(entry["col"])
				rotation = int(entry.get("rotation", 0)) % 360
			except (KeyError, TypeError, ValueError):
				continue

			self.placements.append(Placement(template=template, row=row, col=col, rotation=rotation))
			self.item_available[template] = False

		if self.placements or "placements" in raw:
			self._set_status("Loaded saved inventory.")

	def _save_inventory(self) -> None:
		if self.inventory_save_path.exists() and not messagebox.askyesno(
			"Overwrite saved inventory?",
			"A saved inventory already exists. Overwrite it?",
		):
			return

		data = {
			"grid_rows": self.grid_rows,
			"grid_cols": self.grid_cols,
			"placements": [
				{
					"item_id": placement.template.item_id,
					"row": placement.row,
					"col": placement.col,
					"rotation": placement.rotation,
				}
				for placement in self.placements
			],
		}
		try:
			self.inventory_save_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
		except OSError:
			self._set_status("Could not save the inventory locally.")
			return

		self._set_status("Inventory saved.")

	def _load_templates(self) -> list[ItemTemplate]:
		if not self.storage_path.exists():
			return []

		try:
			raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError):
			return []

		if not isinstance(raw, list):
			return []

		templates: list[ItemTemplate] = []
		for entry in raw:
			if not isinstance(entry, dict):
				continue

			name = str(entry.get("name", "Unnamed Item")).strip() or "Unnamed Item"
			color = str(entry.get("color", "#6b7280")).strip() or "#6b7280"
			mask_data = entry.get("mask", [])
			if not isinstance(mask_data, list):
				continue

			normalized_rows: list[tuple[bool, ...]] = []
			max_width = 0
			for row in mask_data:
				if not isinstance(row, list):
					continue
				row_tuple = tuple(bool(cell) for cell in row)
				if row_tuple:
					max_width = max(max_width, len(row_tuple))
					normalized_rows.append(row_tuple)

			if not normalized_rows or max_width <= 0:
				continue

			mask = tuple(
				tuple(row[index] if index < len(row) else False for index in range(max_width))
				for row in normalized_rows
			)
			mask = self._trim_mask(mask)
			if not mask:
				continue

			template = ItemTemplate(
				item_id=str(entry.get("item_id") or uuid.uuid4()),
				name=name,
				width=len(mask[0]),
				height=len(mask),
				color=color,
				mask=mask,
			)
			templates.append(template)

		return templates

	def _save_templates(self) -> None:
		data = [
			{
				"item_id": template.item_id,
				"name": template.name,
				"width": template.width,
				"height": template.height,
				"color": template.color,
				"mask": [[cell for cell in row] for row in template.mask],
			}
			for template in self.templates
		]
		try:
			self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
		except OSError:
			self._set_status("Could not save custom items locally.")

	def _trim_mask(self, mask: tuple[tuple[bool, ...], ...]) -> tuple[tuple[bool, ...], ...]:
		if not mask:
			return ()

		rows_with_content = [index for index, row in enumerate(mask) if any(row)]
		if not rows_with_content:
			return ()

		top = rows_with_content[0]
		bottom = rows_with_content[-1]

		cols_with_content = [
			index
			for index in range(len(mask[0]))
			if any(row[index] for row in mask)
		]
		if not cols_with_content:
			return ()

		left = cols_with_content[0]
		right = cols_with_content[-1]

		return tuple(
			tuple(row[col] for col in range(left, right + 1))
			for row in mask[top : bottom + 1]
		)

	def _add_custom_template(self, template: ItemTemplate) -> None:
		self.templates.append(template)
		self.item_available[template] = True
		if getattr(self, "empty_sidebar_label", None) is not None:
			self.empty_sidebar_label.destroy()
			self.empty_sidebar_label = None
		self._create_item_card(template)
		self._save_templates()
		self._set_status(f"Created {template.name}.")

	def _update_existing_template(self, old_template: ItemTemplate, new_template: ItemTemplate) -> None:
		try:
			index = self.templates.index(old_template)
		except ValueError:
			self._add_custom_template(new_template)
			return

		old_available = self.item_available.pop(old_template, True)
		self.templates[index] = new_template
		self.item_available[new_template] = old_available

		widgets = self.item_card_widgets.pop(old_template, None)
		if widgets is not None:
			self.item_card_widgets[new_template] = widgets
			self._rebind_item_card(new_template, widgets)
			self._refresh_item_card(new_template)

		for placement in self.placements:
			if placement.template is old_template:
				placement.template = new_template

		self._rebuild_grid()
		self._save_templates()
		self._set_status(f"Updated {new_template.name}.")

	def _rebind_item_card(self, template: ItemTemplate, widgets: dict[str, tk.Widget]) -> None:
		for widget in widgets.values():
			widget.bind("<ButtonPress-1>", lambda event, item=template: self._begin_drag(item, event))
			widget.bind("<Double-Button-1>", lambda event, item=template: self._edit_template(item))
			widget.bind("<Button-3>", lambda event, item=template: self._show_item_context_menu(item, event))

	def _open_item_size_dialog(self) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title("New Item Size")
		dialog.resizable(False, False)
		dialog.transient(self.root)
		dialog.grab_set()

		frame = ttk.Frame(dialog, padding=18)
		frame.pack(fill="both", expand=True)

		ttk.Label(frame, text="Create new item", font=(self.FONT_FAMILY, 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
		ttk.Label(frame, text="Width:").grid(row=1, column=0, sticky="w", pady=4)
		width_var = tk.IntVar(value=8)
		width_spin = tk.Spinbox(frame, from_=1, to=20, textvariable=width_var, width=8)
		width_spin.grid(row=1, column=1, sticky="w", pady=4)

		ttk.Label(frame, text="Height:").grid(row=2, column=0, sticky="w", pady=4)
		height_var = tk.IntVar(value=8)
		height_spin = tk.Spinbox(frame, from_=1, to=20, textvariable=height_var, width=8)
		height_spin.grid(row=2, column=1, sticky="w", pady=4)

		tt = ttk.Label(frame, text="Choose the item size first, then draw the shape on the grid. Empty rows and columns will be removed.", wraplength=280, foreground="#6b7280", font=(self.FONT_FAMILY, 9))
		tt.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 14))

		button_row = ttk.Frame(frame)
		button_row.grid(row=4, column=0, columnspan=2, sticky="e")

		def next_step() -> None:
			try:
				width = max(1, int(width_var.get()))
				height = max(1, int(height_var.get()))
			except (tk.TclError, ValueError):
				messagebox.showerror("Invalid value", "Please enter valid whole numbers.")
				return

			dialog.destroy()
			self._open_item_editor_dialog(width, height)

		ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
		ttk.Button(button_row, text="Next", command=next_step).pack(side="right")

		dialog.update_idletasks()
		x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
		y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
		dialog.geometry(f"+{x}+{y}")

	def _open_item_editor_dialog(self, width: int, height: int, existing_template: Optional[ItemTemplate] = None) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title("Draw item")
		dialog.transient(self.root)
		dialog.grab_set()
		dialog.minsize(420, 360)

		frame = ttk.Frame(dialog, padding=18)
		frame.pack(fill="both", expand=True)

		if existing_template is None:
			item_name_var = tk.StringVar(value=f"New Item {len(self.templates) + 1}")
			color_var = tk.StringVar(value=self._random_color())
			mask = [[False for _ in range(width)] for _ in range(height)]
		else:
			item_name_var = tk.StringVar(value=existing_template.name)
			color_var = tk.StringVar(value=existing_template.color)
			mask = [[cell for cell in row] for row in existing_template.mask]
		cell_size = 28
		cell_rectangles: dict[tuple[int, int], int] = {}
		paint_state: Optional[bool] = None

		ttk.Label(frame, text="Item name:").grid(row=0, column=0, sticky="w", pady=(0, 4))
		name_entry = ttk.Entry(frame, textvariable=item_name_var)
		name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 4))

		ttk.Label(frame, text="Color:").grid(row=1, column=0, sticky="w", pady=4)
		color_entry = ttk.Entry(frame, textvariable=color_var, width=12)
		color_entry.grid(row=1, column=1, sticky="w", pady=4)
		color_preview_label = ttk.Label(frame, text="Preview:")
		color_preview_label.grid(row=1, column=2, sticky="w", padx=(8, 4), pady=4)
		color_preview = tk.Frame(frame, width=36, height=20, bg=color_var.get().strip() or "#7c4dff", highlightthickness=1, highlightbackground="#374151")
		color_preview.grid(row=1, column=3, sticky="w", pady=4)
		color_preview.grid_propagate(False)

		def choose_color() -> None:
			selected = colorchooser.askcolor(color=color_var.get(), parent=dialog)
			if selected and selected[1]:
				color_var.set(selected[1])
				update_color_preview()
				redraw()

		def update_color_preview() -> None:
			color_preview.configure(bg=color_var.get().strip() or "#7c4dff")

		color_var.trace_add("write", lambda *_args: update_color_preview())

		color_button = ttk.Button(frame, text="Pick", command=choose_color)
		color_button.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=4)

		info = ttk.Label(
			frame,
			text="Click and drag on the grid to draw the item shape. Filled cells will use the chosen color.",
			wraplength=340,
			foreground="#6b7280",
		)
		info.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 10))

		grid_canvas = tk.Canvas(frame, width=width * cell_size, height=height * cell_size, bg="white", highlightthickness=0)
		grid_canvas.grid(row=3, column=0, columnspan=3, sticky="nsew")

		frame.columnconfigure(1, weight=1)
		frame.rowconfigure(3, weight=1)

		for row in range(height):
			for col in range(width):
				x1 = col * cell_size
				y1 = row * cell_size
				x2 = x1 + cell_size
				y2 = y1 + cell_size
				rect = grid_canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="#d1d5db")
				cell_rectangles[(row, col)] = rect

		def redraw() -> None:
			fill_color = color_var.get().strip() or "#7c4dff"
			for row in range(height):
				for col in range(width):
					rect = cell_rectangles[(row, col)]
					grid_canvas.itemconfigure(rect, fill=fill_color if mask[row][col] else "white")

		def cell_from_event(event: tk.Event) -> Optional[tuple[int, int]]:
			col = int(event.x // cell_size)
			row = int(event.y // cell_size)
			if 0 <= row < height and 0 <= col < width:
				return row, col
			return None

		def paint_cell(row: int, col: int, state: bool) -> None:
			mask[row][col] = state
			fill_color = (color_var.get().strip() or "#7c4dff") if state else "white"
			grid_canvas.itemconfigure(cell_rectangles[(row, col)], fill=fill_color)

		def on_press(event: tk.Event) -> None:
			nonlocal paint_state
			location = cell_from_event(event)
			if location is None:
				return
			row, col = location
			paint_state = not mask[row][col]
			paint_cell(row, col, paint_state)

		def on_drag(event: tk.Event) -> None:
			nonlocal paint_state
			if paint_state is None:
				return
			location = cell_from_event(event)
			if location is None:
				return
			row, col = location
			paint_cell(row, col, paint_state)

		grid_canvas.bind("<ButtonPress-1>", on_press)
		grid_canvas.bind("<B1-Motion>", on_drag)

		button_row = ttk.Frame(frame)
		button_row.grid(row=4, column=0, columnspan=3, sticky="e", pady=(14, 0))

		def save_item() -> None:
			name = item_name_var.get().strip()
			if not name:
				messagebox.showerror("Missing name", "Please enter an item name.")
				return

			if not any(any(row) for row in mask):
				messagebox.showerror("Empty item", "Draw at least one filled cell.")
				return

			trimmed_mask = self._trim_mask(tuple(tuple(row) for row in mask))
			if not trimmed_mask:
				messagebox.showerror("Empty item", "Draw at least one filled cell.")
				return

			template = ItemTemplate(
				item_id=existing_template.item_id if existing_template is not None else str(uuid.uuid4()),
				name=name,
				width=len(trimmed_mask[0]),
				height=len(trimmed_mask),
				color=color_var.get().strip() or "#7c4dff",
				mask=trimmed_mask,
			)
			if existing_template is None:
				self._add_custom_template(template)
			else:
				self._update_existing_template(existing_template, template)
			dialog.destroy()

		ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(
			side="right", padx=(8, 0)
		)

		save_button = ttk.Button(button_row, text="Save Item", command=save_item)
		save_button.pack(side="right")

		dialog.bind("<Return>", lambda event: save_button.invoke())

		redraw()
		name_entry.focus_set()
		dialog.update_idletasks()
		x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
		y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
		dialog.geometry(f"+{x}+{y}")

		redraw()
		name_entry.focus_set()
		dialog.update_idletasks()
		x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
		y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
		dialog.geometry(f"+{x}+{y}")

	def _random_color(self) -> str:
		return f"#{random.randint(0, 0xFFFFFF):06x}"

	def _set_item_available(self, template: ItemTemplate, available: bool) -> None:
		self.item_available[template] = available
		self._refresh_item_card(template)

	def _refresh_item_card(self, template: ItemTemplate) -> None:
		widgets = self.item_card_widgets.get(template)
		if not widgets:
			return

		available = self.item_available.get(template, True)
		card_bg = "#2b313a" if available else "#1c2027"
		outline = "#424956" if available else "#2d333d"
		name_fg = "white" if available else "#7c8492"
		size_fg = "#cbd5e1" if available else "#5f6672"
		cursor = "hand2" if available else "arrow"

		widgets["card"].configure(bg=card_bg, highlightbackground=outline, cursor=cursor)
		widgets["swatch"].configure(bg=template.color)
		widgets["text_frame"].configure(bg=card_bg)
		widgets["name"].configure(bg=card_bg, fg=name_fg, text=template.name)
		widgets["size"].configure(bg=card_bg, fg=size_fg, text=f"{template.width} x {template.height}")

	def _show_item_context_menu(self, template: ItemTemplate, event: tk.Event) -> None:
		if self.dragging_template is not None:
			self._rotate_drag(90)
			return

		menu = tk.Menu(self.root, tearoff=0)
		menu.add_command(label="Edit", command=lambda: self._edit_template(template))
		menu.add_command(label="Duplicate", command=lambda: self._duplicate_template(template))
		menu.add_command(label="Delete", command=lambda: self._delete_template(template))
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()

	def _edit_template(self, template: ItemTemplate) -> None:
		self._open_item_editor_dialog(template.width, template.height, template)

	def _duplicate_template(self, template: ItemTemplate) -> None:
		new_name = self._unique_item_name(f"{template.name} Copy")
		duplicate = ItemTemplate(
			item_id=str(uuid.uuid4()),
			name=new_name,
			width=template.width,
			height=template.height,
			color=template.color,
			mask=tuple(tuple(row) for row in template.mask),
		)
		self._add_custom_template(duplicate)

	def _delete_template(self, template: ItemTemplate) -> None:
		if not messagebox.askyesno("Delete item", f"Delete {template.name}?"):
			return

		self.dragging_template = None
		self.drag_rotation = 0
		self.drag_preview = None
		self.moving_placement = None
		self.moving_rotation = 0
		self.move_preview = None
		self._clear_preview()
		self._destroy_ghost()
		self._hide_hover_tooltip()

		self.placements = [placement for placement in self.placements if placement.template is not template]
		if template in self.templates:
			self.templates.remove(template)
		self.item_available.pop(template, None)

		widgets = self.item_card_widgets.pop(template, None)
		if widgets:
			for widget in widgets.values():
				widget.destroy()

		if not self.templates and self.empty_sidebar_label is None and self.items_frame is not None:
			self.empty_sidebar_label = ttk.Label(
				self.items_frame,
				text="No items yet. Use + to create one.",
				style="Subtle.TLabel",
				wraplength=230,
				justify="left",
			)
			self.empty_sidebar_label.pack(anchor="w", padx=18, pady=(0, 18))

		self._rebuild_grid()
		self._save_templates()
		self._set_status(f"Deleted {template.name}.")

	def _unique_item_name(self, base_name: str) -> str:
		candidate = base_name
		counter = 2
		existing_names = {template.name for template in self.templates}
		while candidate in existing_names:
			candidate = f"{base_name} {counter}"
			counter += 1
		return candidate

	def _set_status(self, message: str) -> None:
		self.status_var.set(message)

	def _begin_drag(self, template: ItemTemplate, _event: tk.Event) -> None:
		if not self.item_available.get(template, True):
			self._set_status(f"{template.name} is already on the grid.")
			return

		self.dragging_template = template
		self.drag_rotation = 0
		self.drag_preview = None
		self._create_ghost(template, self.drag_rotation)
		self._update_drag_feedback()
		self._set_status(f"Dragging {template.name}. Press A to rotate counter-clockwise, D or right-click to rotate clockwise.")

	def _create_ghost(self, template: ItemTemplate, rotation: int) -> None:
		self._destroy_ghost()

		mask = self._rotated_mask(template, rotation)
		ghost_width, ghost_height = self._mask_dimensions(mask)
		scale = 24
		ghost_w = max(1, ghost_width) * scale
		ghost_h = max(1, ghost_height) * scale

		ghost = tk.Toplevel(self.root)
		ghost.overrideredirect(True)
		ghost.attributes("-topmost", True)
		try:
			ghost.attributes("-alpha", 0.88)
		except tk.TclError:
			pass

		canvas = tk.Canvas(ghost, width=ghost_w, height=ghost_h, highlightthickness=0, bg="white")
		canvas.pack(fill="both", expand=True)

		for row_index, row in enumerate(mask):
			for col_index, filled in enumerate(row):
				if not filled:
					continue
				x1 = col_index * scale + 2
				y1 = row_index * scale + 2
				x2 = x1 + scale - 4
				y2 = y1 + scale - 4
				canvas.create_rectangle(x1, y1, x2, y2, fill=template.color, outline="#1f2937", width=2, tags="ghost_part")

		canvas.create_text(
			ghost_w // 2,
			ghost_h // 2,
			text=f"{ghost_width} x {ghost_height}",
			fill="white",
			font=(self.FONT_FAMILY, 10, "bold"),
			state="hidden",
		)

		self.ghost_window = ghost
		self.ghost_canvas = canvas
		self._update_ghost_position()

	def _current_drag_size(self, template: ItemTemplate, rotation: int) -> tuple[int, int]:
		return self._mask_dimensions(self._rotated_mask(template, rotation))

	def _rotated_mask(self, template: ItemTemplate, rotation: int) -> tuple[tuple[bool, ...], ...]:
		mask = template.mask
		steps = (rotation // 90) % 4
		for _ in range(steps):
			mask = tuple(tuple(row[col] for row in reversed(mask)) for col in range(len(mask[0])))
		return mask

	def _mask_dimensions(self, mask: tuple[tuple[bool, ...], ...]) -> tuple[int, int]:
		return (len(mask[0]) if mask else 0, len(mask))

	def _rotate_drag(self, direction: int) -> None:
		if self.dragging_template is None:
			return

		self.drag_rotation = (self.drag_rotation + direction) % 360
		self._create_ghost(self.dragging_template, self.drag_rotation)
		self._update_drag_feedback()
		rotation_label = self._rotation_label()
		self._set_status(
			f"Dragging {self.dragging_template.name} at {rotation_label}. Press A to rotate counter-clockwise, D or right-click to rotate clockwise."
		)

	def _rotate_moving(self, direction: int) -> None:
		if self.moving_placement is None:
			return

		self.moving_rotation = (self.moving_rotation + direction) % 360
		self._create_ghost(self.moving_placement.template, self.moving_rotation)
		self._update_move_feedback()
		self._set_status(
			f"Moving {self.moving_placement.template.name} at {self.moving_rotation}°. Press A to rotate counter-clockwise, D or right-click to rotate clockwise."
		)

	def _rotation_label(self) -> str:
		return f"{self.drag_rotation}°"

	def _on_global_keypress(self, event: tk.Event) -> None:
		if self.dragging_template is None and self.moving_placement is None:
			return

		key = (event.keysym or "").lower()
		if key == "a":
			if self.dragging_template is not None:
				self._rotate_drag(-90)
			else:
				self._rotate_moving(-90)
		elif key == "d":
			if self.dragging_template is not None:
				self._rotate_drag(90)
			else:
				self._rotate_moving(90)

	def _update_ghost_position(self) -> None:
		if self.ghost_window is None:
			return

		pointer_x, pointer_y = self.root.winfo_pointerxy()
		self.ghost_window.geometry(f"+{pointer_x + 16}+{pointer_y + 16}")

	def _destroy_ghost(self) -> None:
		if self.ghost_window is not None:
			self.ghost_window.destroy()
		self.ghost_window = None
		self.ghost_canvas = None

	def _on_global_motion(self, _event: tk.Event) -> None:
		if self.moving_placement is not None:
			self._update_move_feedback()
			return

		if self.dragging_template is None:
			self._update_hover_tooltip()
			return
		self._update_drag_feedback()

	def _on_global_release(self, _event: tk.Event) -> None:
		if self.moving_placement is not None:
			self._finish_move()
			return

		if self.dragging_template is None:
			return

		target = self.drag_preview
		template = self.dragging_template
		rotation = self.drag_rotation
		placed_size = self._current_drag_size(template, rotation)

		self.dragging_template = None
		self.drag_rotation = 0
		self.drag_preview = None
		self._clear_preview()
		self._destroy_ghost()

		if target is None:
			self._set_status(f"{template.name} was not placed.")
			return

		row, col, valid = target
		if valid and self._place_item(template, row, col, rotation):
			if placed_size[0] != template.width or placed_size[1] != template.height:
				self._set_status(
					f"Placed {template.name} ({placed_size[0]} x {placed_size[1]}) at row {row + 1}, column {col + 1}, rotated {rotation}°."
				)
			else:
				self._set_status(f"Placed {template.name} at row {row + 1}, column {col + 1}.")
		else:
			self._set_status(f"Could not place {template.name} there.")

	def _on_grid_left_press(self, event: tk.Event) -> None:
		if self.dragging_template is not None or self.moving_placement is not None:
			return

		canvas_x = self.grid_canvas.canvasx(event.x)
		canvas_y = self.grid_canvas.canvasy(event.y)
		col = int(canvas_x // self.cell_size)
		row = int(canvas_y // self.cell_size)

		if not (0 <= row < self.grid_rows and 0 <= col < self.grid_cols):
			return

		placement = self.occupancy[row][col]
		if placement is None:
			return

		self.moving_placement = placement
		self.moving_rotation = placement.rotation
		self.move_preview = None
		self.placements = [existing for existing in self.placements if existing is not placement]
		self._rebuild_grid()
		self._create_ghost(placement.template, self.moving_rotation)
		self._update_move_feedback()
		self._set_status(f"Moving {placement.template.name}. Drop it to place it.")

	def _on_grid_left_drag(self, _event: tk.Event) -> None:
		if self.moving_placement is None:
			return
		self._update_move_feedback()

	def _update_move_feedback(self) -> None:
		if self.moving_placement is None:
			return

		self._update_ghost_position()
		pointer_x, pointer_y = self.root.winfo_pointerxy()
		canvas_widget = self.grid_canvas.winfo_containing(pointer_x, pointer_y)
		if canvas_widget is not self.grid_canvas:
			self.move_preview = None
			self._clear_preview()
			self._set_ghost_color(self.moving_placement.template.color)
			return

		local_x = pointer_x - self.grid_canvas.winfo_rootx()
		local_y = pointer_y - self.grid_canvas.winfo_rooty()
		canvas_x = self.grid_canvas.canvasx(local_x)
		canvas_y = self.grid_canvas.canvasy(local_y)
		col = int(canvas_x // self.cell_size)
		row = int(canvas_y // self.cell_size)

		valid = self._can_place(self.moving_placement.template, row, col, self.moving_rotation)
		self.move_preview = (row, col, valid)
		self._draw_preview(self.moving_placement.template, row, col, valid, self.moving_rotation)
		self._set_ghost_color("#ef4444" if not valid else self.moving_placement.template.color)

	def _finish_move(self) -> None:
		placement = self.moving_placement
		if placement is None:
			return

		target = self.move_preview
		self.moving_placement = None
		self.move_preview = None
		self._clear_preview()
		self._destroy_ghost()

		if target is None or not target[2]:
			self.placements.append(Placement(template=placement.template, row=placement.row, col=placement.col, rotation=placement.rotation))
			self._rebuild_grid()
			self._set_status(f"Kept {placement.template.name} in its original position.")
			return

		row, col, _valid = target
		self.placements.append(Placement(template=placement.template, row=row, col=col, rotation=self.moving_rotation))
		self._rebuild_grid()
		self._set_status(f"Moved {placement.template.name} to row {row + 1}, column {col + 1}.")

	def _on_grid_right_click(self, event: tk.Event) -> None:
		if self.dragging_template is not None:
			self._rotate_drag(90)
			return
		if self.moving_placement is not None:
			self._rotate_moving(90)
			return

		canvas_x = self.grid_canvas.canvasx(event.x)
		canvas_y = self.grid_canvas.canvasy(event.y)
		col = int(canvas_x // self.cell_size)
		row = int(canvas_y // self.cell_size)

		if not (0 <= row < self.grid_rows and 0 <= col < self.grid_cols):
			return

		placement = self.occupancy[row][col]
		if placement is None:
			return

		self._remove_placement(placement)
		self._set_status(f"Removed {placement.template.name} from row {row + 1}, column {col + 1}.")

	def _remove_placement(self, placement: Placement) -> None:
		self.placements = [existing for existing in self.placements if existing is not placement]
		self._set_item_available(placement.template, True)
		self._rebuild_grid()
		self._update_hover_tooltip()

	def _on_grid_motion(self, _event: tk.Event) -> None:
		if self.dragging_template is not None:
			return
		self._update_hover_tooltip()

	def _on_grid_leave(self, _event: tk.Event) -> None:
		if self.dragging_template is not None:
			return
		self._hide_hover_tooltip()

	def _update_hover_tooltip(self) -> None:
		if self.dragging_template is not None:
			self._hide_hover_tooltip()
			return

		pointer_x, pointer_y = self.root.winfo_pointerxy()
		canvas_widget = self.grid_canvas.winfo_containing(pointer_x, pointer_y)
		if canvas_widget is not self.grid_canvas:
			self._hide_hover_tooltip()
			return

		local_x = pointer_x - self.grid_canvas.winfo_rootx()
		local_y = pointer_y - self.grid_canvas.winfo_rooty()
		canvas_x = self.grid_canvas.canvasx(local_x)
		canvas_y = self.grid_canvas.canvasy(local_y)

		col = int(canvas_x // self.cell_size)
		row = int(canvas_y // self.cell_size)

		if not (0 <= row < self.grid_rows and 0 <= col < self.grid_cols):
			self._hide_hover_tooltip()
			return

		placement = self.occupancy[row][col]
		if placement is None:
			self._hide_hover_tooltip()
			return

		self._show_hover_tooltip(placement.template.name, pointer_x + 14, pointer_y + 14)

	def _show_hover_tooltip(self, text: str, x: int, y: int) -> None:
		if self.hover_tooltip is None:
			tooltip = tk.Toplevel(self.root)
			tooltip.overrideredirect(True)
			tooltip.attributes("-topmost", True)
			frame = tk.Frame(tooltip, bg="#111827", bd=0, highlightthickness=1, highlightbackground="#374151")
			frame.pack(fill="both", expand=True)
			label = tk.Label(
				frame,
				bg="#111827",
				fg="white",
				font=(self.FONT_FAMILY, 9, "bold"),
				padx=10,
				pady=6,
			)
			label.pack()
			self.hover_tooltip = tooltip
			self.hover_label = label

		if self.hover_label is not None:
			self.hover_label.configure(text=text)
		self.hover_tooltip.geometry(f"+{x}+{y}")

	def _hide_hover_tooltip(self) -> None:
		if self.hover_tooltip is not None:
			self.hover_tooltip.destroy()
		self.hover_tooltip = None
		self.hover_label = None

	def _update_drag_feedback(self) -> None:
		if self.dragging_template is None:
			return

		self._update_ghost_position()

		pointer_x, pointer_y = self.root.winfo_pointerxy()

		canvas_widget = self.grid_canvas.winfo_containing(pointer_x, pointer_y)
		if canvas_widget is not self.grid_canvas:
			self.drag_preview = None
			self._clear_preview()
			self._set_ghost_color(self.dragging_template.color)
			return

		local_x = pointer_x - self.grid_canvas.winfo_rootx()
		local_y = pointer_y - self.grid_canvas.winfo_rooty()
		canvas_x = self.grid_canvas.canvasx(local_x)
		canvas_y = self.grid_canvas.canvasy(local_y)

		col = int(canvas_x // self.cell_size)
		row = int(canvas_y // self.cell_size)

		valid = self._can_place(self.dragging_template, row, col, self.drag_rotation)
		self.drag_preview = (row, col, valid)
		self._draw_preview(self.dragging_template, row, col, valid, self.drag_rotation)
		self._set_ghost_color("#ef4444" if not valid else self.dragging_template.color)

	def _set_ghost_color(self, color: str) -> None:
		if self.ghost_canvas is None:
			return

		self.ghost_canvas.itemconfigure("ghost_part", fill=color)

	def _clear_preview(self) -> None:
		self.grid_canvas.delete("preview")

	def _draw_preview(self, template: ItemTemplate, row: int, col: int, valid: bool, rotation: int) -> None:
		self._clear_preview()

		preview_color = "#10b981" if valid else "#ef4444"
		mask = self._rotated_mask(template, rotation)
		for mask_row, mask_values in enumerate(mask):
			for mask_col, filled in enumerate(mask_values):
				if not filled:
					continue
				r = row + mask_row
				c = col + mask_col
				if not (0 <= r < self.grid_rows and 0 <= c < self.grid_cols):
					continue
				x1 = c * self.cell_size + 1
				y1 = r * self.cell_size + 1
				x2 = x1 + self.cell_size - 2
				y2 = y1 + self.cell_size - 2
				self.grid_canvas.create_rectangle(
					x1,
					y1,
					x2,
					y2,
					fill=preview_color,
					outline=preview_color,
					width=2,
					stipple="gray50",
					tags="preview",
				)

	def _update_scroll_region(self) -> None:
		width = self.grid_cols * self.cell_size
		height = self.grid_rows * self.cell_size
		self.grid_canvas.configure(scrollregion=(0, 0, width, height))

	def _can_place(self, template: ItemTemplate, row: int, col: int, rotation: int = 0) -> bool:
		mask = self._rotated_mask(template, rotation)
		width, height = self._mask_dimensions(mask)
		if row < 0 or col < 0:
			return False
		if row + height > self.grid_rows or col + width > self.grid_cols:
			return False

		for mask_row, mask_values in enumerate(mask):
			for mask_col, filled in enumerate(mask_values):
				if not filled:
					continue
				r = row + mask_row
				c = col + mask_col
				if self.occupancy[r][c] is not None:
					return False
		return True

	def _place_item(self, template: ItemTemplate, row: int, col: int, rotation: int) -> bool:
		if not self._can_place(template, row, col, rotation):
			return False

		self.placements.append(Placement(template=template, row=row, col=col, rotation=rotation))
		self._set_item_available(template, False)
		self._rebuild_grid()
		return True

	def _rebuild_grid(self) -> int:
		old_placements = list(self.placements)
		self.occupancy = [[None for _ in range(self.grid_cols)] for _ in range(self.grid_rows)]
		kept: list[Placement] = []
		removed = 0

		for placement in self.placements:
			if self._can_place(placement.template, placement.row, placement.col, placement.rotation):
				kept.append(placement)
				mask = self._rotated_mask(placement.template, placement.rotation)
				for mask_row, mask_values in enumerate(mask):
					for mask_col, filled in enumerate(mask_values):
						if filled:
							self.occupancy[placement.row + mask_row][placement.col + mask_col] = placement
			else:
				removed += 1

		for placement in old_placements:
			if placement not in kept:
				self._set_item_available(placement.template, True)

		self.placements = kept

		self._draw_grid()
		self._update_scroll_region()
		return removed

	def _draw_grid(self) -> None:
		self.grid_canvas.delete("all")
		self.cell_rectangles.clear()

		for row in range(self.grid_rows):
			for col in range(self.grid_cols):
				x1 = col * self.cell_size
				y1 = row * self.cell_size
				x2 = x1 + self.cell_size
				y2 = y1 + self.cell_size

				placement = self.occupancy[row][col]
				fill = placement.template.color if placement is not None else "#ffffff"
				outline = "#9ca3af" if placement is not None else "#d1d5db"
				rect = self.grid_canvas.create_rectangle(
					x1,
					y1,
					x2,
					y2,
					fill=fill,
					outline=outline,
					width=1,
				)
				self.cell_rectangles[(row, col)] = rect


def main() -> None:
	root = tk.Tk()
	EbInventoryGridApp(root)
	root.mainloop()


if __name__ == "__main__":
	main()

