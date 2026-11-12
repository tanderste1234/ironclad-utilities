# ©Thomas Edmund Anderson 2026
import multiprocessing
import os
import sys
import re
import csv
import hashlib
import time
import psutil
import duckdb
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def calculate_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    if not os.path.exists(file_path):
        return hashlib.sha256(b"CSV_TOOL_DEFAULT_EULA_2026").hexdigest()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return ""


def on_eula_complete(parent, accepted):
    if not accepted:
        try:
            parent.destroy()
        except Exception:
            pass


def check_and_prompt_eula(parent, eula_file_path="EULA.txt",
                          flag_file_path=".eula_accepted", on_complete_callback=None):
    if not os.path.exists(eula_file_path):
        try:
            parent.destroy()
        except Exception:
            pass
        messagebox.showerror(
            "Setup Error - Unauthorized Access",
            "Error: The EULA.txt file is missing.\n\n"
            "The tool is not correctly set up because you did not use the official installer. "
            "As such, you are not legally allowed to use this software."
        )
        sys.exit(0)

    current_eula_hash = calculate_file_hash(eula_file_path)
    if os.path.exists(flag_file_path):
        try:
            with open(flag_file_path, "r", encoding="utf-8") as f:
                content = f.read()
                stored_hash = ""
                for line in content.splitlines():
                    if line.startswith("EULA_HASH="):
                        stored_hash = line.split("=", 1)[1].strip()
                if stored_hash and stored_hash == current_eula_hash:
                    return True
        except Exception:
            pass

    try:
        with open(eula_file_path, "r", encoding="utf-8") as f:
            eula_content = f.read()
    except Exception:
        eula_content = "Failed to load EULA file."

    eula_accepted = [False]
    dialog = tk.Toplevel(parent)
    dialog.title("End User License Agreement - CSV Tool")
    dialog.geometry("600x500")
    dialog.transient(parent)
    dialog.grab_set()

    def handle_exit_without_agreement():
        messagebox.showinfo(
            "License Required",
            "Acceptance of the End User License Agreement is required to operate CSV Tool.\n\nThe application will now close."
        )
        dialog.destroy()
        parent.destroy()

    dialog.protocol("WM_DELETE_WINDOW", handle_exit_without_agreement)

    lbl_title = ttk.Label(dialog, text="An updated End User License Agreement requires your acceptance (Please scroll to the bottom):", font=("Helvetica", 10, "bold"))
    lbl_title.pack(anchor=tk.W, padx=10, pady=(10, 5))

    txt_frame = ttk.Frame(dialog, padding="5")
    txt_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    scrollbar = ttk.Scrollbar(txt_frame, orient=tk.VERTICAL)
    txt_area = tk.Text(txt_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=("Consolas", 9))
    scrollbar.config(command=txt_area.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    txt_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    txt_area.insert(tk.END, eula_content)
    txt_area.config(state="disabled")

    btn_frame = ttk.Frame(dialog, padding="10")
    btn_frame.pack(fill=tk.X)

    def on_accept():
        eula_accepted[0] = True
        try:
            with open(flag_file_path, "w", encoding="utf-8") as flag_file:
                flag_file.write(f"ACCEPTED=TRUE\nDATE=2026\nEULA_HASH={current_eula_hash}\n")
        except Exception:
            pass
        dialog.destroy()

    btn_decline = ttk.Button(btn_frame, text="Decline & Exit", command=handle_exit_without_agreement)
    btn_decline.pack(side=tk.LEFT, padx=10)
    btn_accept = ttk.Button(btn_frame, text="I Accept the Terms", command=on_accept, state="disabled")
    btn_accept.pack(side=tk.RIGHT, padx=10)
    
    def check_scroll(*args):
        fraction = scrollbar.get()
        if fraction[1] >= 0.999:
            btn_accept.config(state="normal")
            lbl_title.config(text="End User License Agreement:")

    scrollbar.config(command=lambda *args: [txt_area.yview(*args), check_scroll()])
    
    def on_text_scroll(event):
        dialog.after_idle(check_scroll)

    txt_area.bind("<MouseWheel>", on_text_scroll)
    txt_area.bind("<Button-4>", on_text_scroll)
    txt_area.bind("<Button-5>", on_text_scroll)
    txt_area.bind("<Key>", on_text_scroll)

    dialog.after(200, check_scroll)
    parent.wait_window(dialog)
    return eula_accepted[0]


def extract_file_sort_key(file_path):
    """
    Extracts the (year, day_number) integer tuple from filenames formatted like:
    'CSV_7493.flux_2022_135_0900.csv'.
    Returns (year, day) to allow multi-year ascending chronological sorting.
    """
    filename = os.path.basename(file_path)
    
    match = re.search(r'_(\d{4})_(\d{1,3})_\d{4}(?:\.csv)?$', filename, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        day = int(match.group(2))
        return (year, day)

    parts = filename.replace('.csv', '').split('_')
    if len(parts) >= 5:
        try:
            year = int(parts[2])
            day = int(parts[3])
            return (year, day)
        except ValueError:
            pass

    fallback_match = re.search(r'(\d{4})_(\d{1,3})', filename)
    if fallback_match:
        try:
            return (int(fallback_match.group(1)), int(fallback_match.group(2)))
        except ValueError:
            pass

    return (0, 0)


def get_headers_from_template(template_path="templateFile.csv"):
    """Reads the first line of the template file to extract column headers."""
    if not os.path.exists(template_path):
        return None
    try:
        with open(template_path, mode="r", newline="", encoding="utf-8-sig", errors="ignore") as file:
            reader = csv.reader(file)
            headers = next(reader)
            cleaned_headers = [h.strip() for h in headers if h.strip()]
            return cleaned_headers
    except Exception:
        return None


def get_current_process_memory_mb():
    try:
        proc = psutil.Process(os.getpid())
        return proc.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def write_performance_report_csv(report_filename, metrics_data):
    file_exists = os.path.exists(report_filename)
    try:
        with open(report_filename, mode="a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            if not file_exists:
                writer.writerow([
                    "Timestamp", "Source_Type", "Execution_Time_Seconds", 
                    "Rows_Written", "Processing_Rate_Rows_Per_Sec", 
                    "Peak_RAM_MB"
                ])
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                metrics_data.get("source_type", "RDTool"),
                f"{metrics_data.get('elapsed_time', 0.0):.2f}",
                metrics_data.get("rows_written", 0),
                f"{metrics_data.get('rows_per_sec', 0.0):.2f}",
                f"{metrics_data.get('peak_memory', 0.0):.2f}"
            ])
    except Exception:
        pass


def merge_headless_csvs_duckdb(
    file_paths,
    output_path,
    template_path="templateFile.csv",
    order_direction="ASC",
    enable_metrics=False,
    debug_func=print
):
    """
    High-performance, low-memory CSV merger using DuckDB.
    Isolates the dominant year, applies template headers, ALWAYS deduplicates 
    timestamp overlaps, sorts by Day and Time (ASC or DESC), and streams output directly to disk.
    """
    start_time = time.perf_counter() if enable_metrics else 0
    initial_mem = get_current_process_memory_mb() if enable_metrics else 0.0

    if not file_paths:
        if debug_func:
            debug_func("ERROR: No input files provided.")
        return False

    if enable_metrics and debug_func:
        debug_func(f"[METRIC] Initial RAM Allocation: {initial_mem:.2f} MB")

    sort_dir = "DESC" if str(order_direction).upper().startswith("REV") or str(order_direction).upper() == "DESC" else "ASC"

    file_paths = list(file_paths)
    file_paths.sort(key=extract_file_sort_key)

    if debug_func:
        debug_func("Sorted execution queue (ascending by Year, then Day Number):")
        for f in file_paths:
            year, day_num = extract_file_sort_key(f)
            debug_func(f"  - Year {year}, Day {day_num}: {os.path.basename(f)}")

    formatted_paths = [f"'{os.path.abspath(p).replace(os.sep, '/')}'" for p in file_paths]
    files_list_sql = ", ".join(formatted_paths)

    con = duckdb.connect(database=":memory:")

    try:
        if debug_func:
            debug_func("Analyzing input files via DuckDB engine...")

        raw_view_query = f"""
            CREATE TEMP VIEW raw_data AS 
            SELECT * FROM read_csv([
                {files_list_sql}
            ], header=False, all_varchar=True, ignore_errors=True);
        """
        con.execute(raw_view_query)

        col_names = [col[0] for col in con.execute("DESCRIBE raw_data").fetchall()]
        num_columns = len(col_names)

        template_headers = get_headers_from_template(template_path)
        if template_headers and len(template_headers) == num_columns:
            headers = template_headers
        else:
            if template_headers and debug_func:
                debug_func(f"WARNING: Template column count ({len(template_headers)}) does not match data column count ({num_columns}). Using default headers.")
            headers = ["Year", "Day", "Time"] + [f"Data_{i - 2}" for i in range(3, num_columns)]

        year_col = col_names[0]
        year_counts = con.execute(f"""
            SELECT TRIM({year_col}) AS yr, COUNT(*) as cnt 
            FROM raw_data 
            WHERE {year_col} IS NOT NULL AND TRIM({year_col}) != ''
            GROUP BY yr 
            ORDER BY cnt DESC;
        """).fetchall()

        if not year_counts:
            if debug_func:
                debug_func("ERROR: No valid data found in input files.")
            return False

        dominant_year = year_counts[0][0]
        dominant_count = year_counts[0][1]

        if debug_func:
            debug_func("Year Distribution Found:")
            for yr, count in year_counts:
                debug_func(f"  - Year {yr}: {count:,} rows")
            debug_func(f"KEEPING DOMINANT YEAR: {dominant_year} ({dominant_count:,} rows). Discarding other years.")

        col_select_list = []
        for orig_col, header_name in zip(col_names, headers):
            clean_header = header_name.replace('"', '""')
            col_select_list.append(f'{orig_col} AS "{clean_header}"')
        col_select_sql = ", ".join(col_select_list)

        c0, c1, c2 = col_names[0], col_names[1], col_names[2]
        if num_columns >= 3:
            if debug_func:
                debug_func(f"Deduplicating timestamp overlaps & sorting ({sort_dir}) for Year {dominant_year}...")
            
            export_sql = f"""
                SELECT {col_select_sql}
                FROM raw_data
                WHERE TRIM({c0}) = '{dominant_year}'
                QUALIFY ROW_NUMBER() OVER(PARTITION BY TRIM({c0}), TRIM({c1}), TRIM({c2})) = 1
                ORDER BY TRY_CAST(TRIM({c1}) AS INTEGER) {sort_dir}, TRY_CAST(TRIM({c2}) AS INTEGER) {sort_dir}
            """
        else:
            export_sql = f"""
                SELECT {col_select_sql}
                FROM raw_data
                WHERE TRIM({c0}) = '{dominant_year}'
                ORDER BY TRY_CAST(TRIM({c1}) AS INTEGER) {sort_dir}
            """

        output_abs_path = os.path.abspath(output_path).replace(os.sep, '/')
        copy_query = f"""
            COPY ({export_sql}) 
            TO '{output_abs_path}' 
            (HEADER, DELIMITER ',');
        """

        if debug_func:
            debug_func(f"Streaming single-year output file to disk: {output_path}")

        con.execute(copy_query)

        written_rows = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{output_abs_path}')").fetchone()[0]
        
        if debug_func:
            debug_func(f"SUCCESS: Wrote {written_rows:,} valid rows for Year {dominant_year} to '{os.path.basename(output_path)}'.")

        peak_mem = get_current_process_memory_mb() if enable_metrics else 0.0
        elapsed_time = time.perf_counter() - start_time if enable_metrics else 0.0
        rows_per_sec = written_rows / elapsed_time if (enable_metrics and elapsed_time > 0) else 0.0

        if enable_metrics and debug_func:
            debug_func("==================================================")
            debug_func("            BENCHMARK PERFORMANCE METRICS         ")
            debug_func("==================================================")
            debug_func(f"Execution Time    : {elapsed_time:.2f} seconds")
            debug_func(f"Rows Written      : {written_rows:,}")
            debug_func(f"Processing Rate   : {rows_per_sec:,.0f} rows/sec")
            debug_func(f"Peak RAM Usage    : {peak_mem:.2f} MB")
            debug_func("==================================================")

            report_data = {
                "source_type": "RDTool_DominantYearIsolator",
                "elapsed_time": elapsed_time,
                "rows_written": written_rows,
                "rows_per_sec": rows_per_sec,
                "peak_memory": peak_mem
            }
            write_performance_report_csv("rdtool_performance_report.csv", report_data)
            debug_func("[METRIC] Performance report appended to 'rdtool_performance_report.csv'.")

        return True

    except Exception as e:
        if debug_func:
            debug_func(f"ERROR executing DuckDB processing engine: {str(e)}")
        return False
    finally:
        con.close()


def create_application():
    root = tk.Tk()
    root.title("RDTOOL V1.3.2 (Dominant Year Isolator)")
    root.after(100, lambda: check_and_prompt_eula(root, on_complete_callback=on_eula_complete))

    width = 650
    collapsed_height = 420
    expanded_height = 580

    root.geometry(f"{width}x{collapsed_height}")
    root.minsize(width, collapsed_height)

    state = {
        "input_files": [],
        "show_debug": False
    }

    main_frame = ttk.Frame(root, padding="12")
    main_frame.pack(fill=tk.BOTH, expand=True)

    file_frame = ttk.LabelFrame(main_frame, text="Input Headless Files", padding="8")
    file_frame.pack(fill=tk.BOTH, expand=True, pady=4)

    listbox = tk.Listbox(file_frame, selectmode=tk.EXTENDED, height=6)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

    scrollbar = ttk.Scrollbar(file_frame, orient=tk.VERTICAL, command=listbox.yview)
    scrollbar.pack(side=tk.LEFT, fill=tk.Y)
    listbox.config(yscrollcommand=scrollbar.set)

    btn_stack = ttk.Frame(file_frame)
    btn_stack.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

    log_frame = ttk.LabelFrame(main_frame, text="Execution Debug Log", padding="6")
    log_text = tk.Text(log_frame, wrap=tk.WORD, height=8, bg="#1e1e1e", fg="#00ff00")
    log_text.pack(fill=tk.BOTH, expand=True)

    def log(message):
        log_text.insert(tk.END, str(message) + "\n")
        log_text.see(tk.END)

    def toggle_debug():
        state["show_debug"] = not state["show_debug"]
        if state["show_debug"]:
            root.minsize(width, expanded_height)
            log_frame.pack(fill=tk.BOTH, expand=True, pady=4)
            toggle_btn.config(text="Hide Debug Log ▼")
            root.geometry(f"{width}x{expanded_height}")
        else:
            log_frame.pack_forget()
            toggle_btn.config(text="Show Debug Log ▲")
            root.geometry(f"{width}x{collapsed_height}")
            root.minsize(width, collapsed_height)

    def add_files():
        paths = filedialog.askopenfilenames(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if paths:
            for p in paths:
                if p not in state["input_files"]:
                    state["input_files"].append(p)
                    listbox.insert(tk.END, p)

    def remove_selected():
        selected_indices = list(listbox.curselection())
        selected_indices.reverse()
        for idx in selected_indices:
            del state["input_files"][idx]
            listbox.delete(idx)

    def clear_all():
        state["input_files"].clear()
        listbox.delete(0, tk.END)

    def browse_template():
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if path:
            template_entry.delete(0, tk.END)
            template_entry.insert(0, path)

    def browse_output():
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if path:
            output_entry.delete(0, tk.END)
            output_entry.insert(0, path)

    def process():
        output_path = output_entry.get().strip()
        template_path = template_entry.get().strip()
        selected_order = order_var.get()
        enable_metrics = enable_metrics_var.get()

        if not state["input_files"]:
            messagebox.showerror("Error", "Please add at least one input CSV file.")
            return

        if not output_path:
            messagebox.showerror("Error", "Please specify an output CSV file destination.")
            return

        log_text.delete("1.0", tk.END)
        success = merge_headless_csvs_duckdb(
            state["input_files"],
            output_path,
            template_path=template_path,
            order_direction=selected_order,
            enable_metrics=enable_metrics,
            debug_func=log
        )

        if success and not state["show_debug"]:
            messagebox.showinfo("Success", f"Output file created successfully:\n{os.path.basename(output_path)}")

    ttk.Button(btn_stack, text="Add Files...", command=add_files).pack(fill=tk.X, pady=2)
    ttk.Button(btn_stack, text="Remove Selected", command=remove_selected).pack(fill=tk.X, pady=2)
    ttk.Button(btn_stack, text="Clear All", command=clear_all).pack(fill=tk.X, pady=2)

    config_frame = ttk.Frame(main_frame, padding="4")
    config_frame.pack(fill=tk.X, pady=2)
    config_frame.columnconfigure(1, weight=1)

    ttk.Label(config_frame, text="Header Template CSV:").grid(row=0, column=0, sticky=tk.W)
    template_entry = ttk.Entry(config_frame)
    template_entry.insert(0, "templateFile.csv")
    template_entry.grid(row=0, column=1, padx=5, sticky=tk.EW)
    ttk.Button(config_frame, text="Browse...", command=browse_template).grid(row=0, column=2)

    ttk.Label(config_frame, text="Export Order:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
    order_var = tk.StringVar(value="Chronological")
    order_dropdown = ttk.Combobox(
        config_frame, 
        textvariable=order_var, 
        values=["Chronological", "Reverse Chronological"], 
        state="readonly",
        width=22
    )
    order_dropdown.grid(row=1, column=1, padx=5, pady=(5, 0), sticky=tk.W)

    output_frame = ttk.Frame(main_frame, padding="4")
    output_frame.pack(fill=tk.X, pady=2)
    output_frame.columnconfigure(1, weight=1)

    ttk.Label(output_frame, text="Output CSV File:").grid(row=0, column=0, sticky=tk.W)
    output_entry = ttk.Entry(output_frame)
    output_entry.grid(row=0, column=1, padx=5, sticky=tk.EW)
    ttk.Button(output_frame, text="Browse...", command=browse_output).grid(row=0, column=2)

    # --- Metrics Opt-In/Opt-Out Option Frame (Off by Default) ---
    options_frame = ttk.Frame(main_frame, padding="2")
    options_frame.pack(fill=tk.X, pady=2)

    enable_metrics_var = tk.BooleanVar(value=False)
    metrics_check = ttk.Checkbutton(
        options_frame, 
        text="Enable Local Performance & Diagnostic Metrics Logging", 
        variable=enable_metrics_var
    )
    metrics_check.pack(anchor=tk.W, padx=2, pady=2)

    control_frame = ttk.Frame(main_frame, padding="4")
    control_frame.pack(fill=tk.X, pady=6)

    ttk.Button(control_frame, text="Filter & Export Most Frequent Year", command=process).pack(side=tk.LEFT, padx=5)

    toggle_btn = ttk.Button(control_frame, text="Show Debug Log ▲", command=toggle_debug)
    toggle_btn.pack(side=tk.RIGHT, padx=5)

    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    create_application()