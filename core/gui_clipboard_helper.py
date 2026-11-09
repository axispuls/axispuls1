import tkinter as tk
from typing import Any, Optional
import customtkinter as ctk

def _get_target_entry_or_text(widget: Any) -> Optional[tk.Widget]:
    """
    Returns the underlying Tkinter Entry or Text widget if widget is
    CTkEntry, CTkTextbox, or a native Entry/Text.
    """
    if hasattr(widget, "_entry"):
        return widget._entry
    if hasattr(widget, "_textbox"):
        return widget._textbox
    if isinstance(widget, (tk.Entry, tk.Text)):
        return widget
    return None

def show_context_menu(event: Any, target_widget: Optional[tk.Widget] = None):
    """
    Pops up a full Persian right-click context menu with Paste, Copy, Cut, Select All, and Clear.
    """
    w = target_widget or _get_target_entry_or_text(event.widget)
    if not w:
        return

    try:
        w.focus_set()
    except Exception:
        pass

    # If it's an Entry and nothing is selected, move the insertion cursor to click position
    if isinstance(w, tk.Entry):
        try:
            if not w.select_present():
                idx = w.index(f"@{event.x}")
                w.icursor(idx)
        except Exception:
            pass

    menu = tk.Menu(
        w,
        tearoff=0,
        font=("Tahoma", 10),
        bg="#FFFFFF",
        fg="#0F172A",
        activebackground="#0284C7",
        activeforeground="#FFFFFF"
    )

    def do_paste():
        try:
            text = w.clipboard_get()
            if not text:
                return
            if isinstance(w, tk.Entry):
                try:
                    if w.select_present():
                        w.delete("sel.first", "sel.last")
                except Exception:
                    pass
                w.insert(tk.INSERT, text)
            elif isinstance(w, tk.Text):
                try:
                    sel = w.tag_ranges(tk.SEL)
                    if sel:
                        w.delete(sel[0], sel[1])
                except Exception:
                    pass
                w.insert(tk.INSERT, text)
        except Exception:
            pass

    def do_copy():
        try:
            text = ""
            if isinstance(w, tk.Entry):
                if w.select_present():
                    text = w.selection_get()
                else:
                    text = w.get()
            elif isinstance(w, tk.Text):
                try:
                    text = w.get(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception:
                    text = w.get("1.0", tk.END).strip()
            if text:
                w.clipboard_clear()
                w.clipboard_append(text)
        except Exception:
            pass

    def do_cut():
        try:
            text = ""
            if isinstance(w, tk.Entry):
                if w.select_present():
                    text = w.selection_get()
                    w.delete("sel.first", "sel.last")
                else:
                    text = w.get()
                    w.delete(0, tk.END)
            elif isinstance(w, tk.Text):
                try:
                    text = w.get(tk.SEL_FIRST, tk.SEL_LAST)
                    w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception:
                    text = w.get("1.0", tk.END)
                    w.delete("1.0", tk.END)
            if text:
                w.clipboard_clear()
                w.clipboard_append(text)
        except Exception:
            pass

    def do_select_all():
        try:
            if isinstance(w, tk.Entry):
                w.select_range(0, tk.END)
                w.icursor(tk.END)
            elif isinstance(w, tk.Text):
                w.tag_add(tk.SEL, "1.0", tk.END)
                w.mark_set(tk.INSERT, "1.0")
                w.see(tk.INSERT)
        except Exception:
            pass

    def do_clear():
        try:
            if isinstance(w, tk.Entry):
                if w.select_present():
                    w.delete("sel.first", "sel.last")
                else:
                    w.delete(0, tk.END)
            elif isinstance(w, tk.Text):
                w.delete("1.0", tk.END)
        except Exception:
            pass

    # Check clipboard content
    has_clip = False
    try:
        has_clip = bool(w.clipboard_get())
    except Exception:
        has_clip = False

    # Check selection
    has_sel = False
    try:
        if isinstance(w, tk.Entry):
            has_sel = w.select_present()
        elif isinstance(w, tk.Text):
            has_sel = bool(w.tag_ranges(tk.SEL))
    except Exception:
        has_sel = False

    menu.add_command(
        label="📋 جای‌گذاری (Paste)  Ctrl+V",
        command=do_paste,
        state=tk.NORMAL if has_clip else tk.DISABLED
    )
    menu.add_command(
        label="📄 کپی (Copy)  Ctrl+C",
        command=do_copy
    )
    menu.add_command(
        label="✂️ برش (Cut)  Ctrl+X",
        command=do_cut
    )
    menu.add_separator()
    menu.add_command(
        label="📑 انتخاب همه (Select All)  Ctrl+A",
        command=do_select_all
    )
    menu.add_command(
        label="🗑️ پاک کردن (Clear)",
        command=do_clear
    )

    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()

def attach_entry_context_menu(widget: Any):
    """
    Attaches right-click menu to a CTkEntry, CTkTextbox, tk.Entry, or tk.Text.
    Handles both wrapper and inner widget.
    """
    inner = _get_target_entry_or_text(widget)

    def _handler(event):
        show_context_menu(event, inner or widget)
        return "break"

    try:
        widget.bind("<Button-3>", _handler, add="+")
    except Exception:
        pass

    if inner and inner != widget:
        try:
            inner.bind("<Button-3>", _handler, add="+")
        except Exception:
            pass

def setup_global_clipboard_shortcuts(root: tk.Misc):
    """
    Installs global Windows keycode-based shortcuts on the root window so that
    Ctrl+V, Ctrl+C, Ctrl+X, and Ctrl+A work even when the Windows keyboard layout
    is set to Persian (Farsi) or any non-English layout.
    Also handles global Button-3 (Right Click) for any entry widget.
    """
    def _on_key(event):
        # Check if Control is held down:
        # On Windows, Control mask is 0x4 (or event.state & 4)
        is_ctrl = bool(event.state & 0x0004) or (hasattr(event, "keysym") and "Control" in event.keysym)
        if not is_ctrl:
            return

        # Keycodes on Windows:
        # V = 86, C = 67, X = 88, A = 65
        code = getattr(event, "keycode", None)
        keysym = (getattr(event, "keysym", "") or "").lower()

        # Target focused widget
        try:
            focus_w = root.focus_get()
        except Exception:
            focus_w = None

        target = _get_target_entry_or_text(focus_w)
        if not target:
            return

        # Paste (V / keycode 86)
        if code == 86 or keysym in ("v", "arabic_reh"):
            try:
                clip_text = target.clipboard_get()
                if clip_text:
                    if isinstance(target, tk.Entry):
                        if target.select_present():
                            target.delete("sel.first", "sel.last")
                        target.insert(tk.INSERT, clip_text)
                    elif isinstance(target, tk.Text):
                        sel = target.tag_ranges(tk.SEL)
                        if sel:
                            target.delete(sel[0], sel[1])
                        target.insert(tk.INSERT, clip_text)
                    return "break"
            except Exception:
                pass

        # Copy (C / keycode 67)
        elif code == 67 or keysym in ("c", "arabic_waw"):
            try:
                text = ""
                if isinstance(target, tk.Entry):
                    if target.select_present():
                        text = target.selection_get()
                elif isinstance(target, tk.Text):
                    sel = target.tag_ranges(tk.SEL)
                    if sel:
                        text = target.get(sel[0], sel[1])
                if text:
                    target.clipboard_clear()
                    target.clipboard_append(text)
                    return "break"
            except Exception:
                pass

        # Cut (X / keycode 88)
        elif code == 88 or keysym in ("x", "arabic_hamza"):
            try:
                text = ""
                if isinstance(target, tk.Entry):
                    if target.select_present():
                        text = target.selection_get()
                        target.delete("sel.first", "sel.last")
                elif isinstance(target, tk.Text):
                    sel = target.tag_ranges(tk.SEL)
                    if sel:
                        text = target.get(sel[0], sel[1])
                        target.delete(sel[0], sel[1])
                if text:
                    target.clipboard_clear()
                    target.clipboard_append(text)
                    return "break"
            except Exception:
                pass

        # Select All (A / keycode 65)
        elif code == 65 or keysym in ("a", "arabic_sheen"):
            try:
                if isinstance(target, tk.Entry):
                    target.select_range(0, tk.END)
                    target.icursor(tk.END)
                    return "break"
                elif isinstance(target, tk.Text):
                    target.tag_add(tk.SEL, "1.0", tk.END)
                    target.mark_set(tk.INSERT, "1.0")
                    target.see(tk.INSERT)
                    return "break"
            except Exception:
                pass

    def _on_global_right_click(event):
        target = _get_target_entry_or_text(event.widget)
        if target:
            show_context_menu(event, target)
            return "break"

    try:
        root.bind_all("<KeyPress>", _on_key, add="+")
        root.bind_all("<Button-3>", _on_global_right_click, add="+")
    except Exception:
        pass
