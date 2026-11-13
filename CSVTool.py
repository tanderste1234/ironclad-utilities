# ©Thomas Edmund Anderson 2026
import multiprocessing
import os
import sys
import csv
import calendar
import threading
import shutil
import gc
import hashlib
import time
import psutil
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd

try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# ---------------------------------------------------------------------------
# CORE PARSING & PROCESSING FUNCTIONS
# ---------------------------------------------------------------------------

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
                    "Timestamp", "Execution_Time_Seconds", 
                    "Rows_Processed", "Rows_Written", "Processing_Rate_Rows_Per_Sec", 
                    "Peak_RAM_MB"
                ])
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                f"{metrics_data.get('elapsed_time', 0.0):.2f}",
                metrics_data.get("rows_processed", 0),
                metrics_data.get("rows_written", 0),
                f"{metrics_data.get('rows_per_sec', 0.0):.2f}",
                f"{metrics_data.get('peak_memory', 0.0):.2f}"
            ])
    except Exception:
        pass


def sanitize_text(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def get_headers_from_file(file_path, order_matters=False, multiple_dates=False):
    if not os.path.exists(file_path):
        return None
    raw_headers = []
    try:
        df = pd.read_csv(file_path, nrows=0, encoding="utf-8-sig", low_memory=False, mangle_dupe_cols=False)
        raw_headers = [str(col).strip() for col in df.columns if str(col).strip()]
    except Exception:
        try:
            with open(file_path, mode="r", newline="", encoding="utf-8-sig", errors="ignore") as file:
                reader = csv.reader(file)
                for row in reader:
                    cleaned_row = [item.strip() for item in row if item.strip()]
                    if cleaned_row:
                        raw_headers = cleaned_row
                        break
        except Exception:
            pass

    if not raw_headers:
        return None

    if not order_matters:
        return list(dict.fromkeys(raw_headers))
    else:
        processed_headers = []
        counts = {}
        for h in raw_headers:
            if h in counts:
                counts[h] += 1
                processed_headers.append(f"{h}.{counts[h]}")
            else:
                counts[h] = 1
                processed_headers.append(h)
        return processed_headers


def convert_user_format_to_python(fmt):
    if not fmt:
        return "%Y/%m/%d"
    converted = fmt.replace("YYYY", "%Y").replace("YY", "%y")
    converted = converted.replace("MM", "%m").replace("M", "%m")
    converted = converted.replace("DD", "%d").replace("D", "%d")
    return converted


def convert_output_format_to_strftime(fmt):
    if not fmt:
        return "%m/%d/%Y"
    converted = fmt.replace("YYYY", "%Y").replace("YY", "%y")
    converted = converted.replace("MM", "%m").replace("M", "%m")
    converted = converted.replace("DD", "%d").replace("D", "%d")
    return converted


def parse_date_range(start_str, end_str, debug_func=print):
    if not start_str and not end_str:
        return []

    raw_starts = [item.strip() for item in start_str.split(",") if item.strip()] if start_str else []
    raw_ends = [item.strip() for item in end_str.split(",") if item.strip()] if end_str else []

    max_len = max(len(raw_starts), len(raw_ends))
    if max_len == 0:
        return []

    while len(raw_starts) < max_len:
        raw_starts.append("")
    while len(raw_ends) < max_len:
        raw_ends.append("")

    parsed_ranges = []
    for idx in range(max_len):
        c_start = raw_starts[idx]
        c_end = raw_ends[idx]

        s_dt = None
        e_dt = None

        if c_start:
            s_dt = pd.to_datetime(c_start, format="%m/%d/%Y", errors="coerce")
            if pd.notna(s_dt):
                s_dt = s_dt.floor("D")

        if c_end:
            e_dt = pd.to_datetime(c_end, format="%m/%d/%Y", errors="coerce")
            if pd.notna(e_dt):
                e_dt = e_dt.floor("D")

        if s_dt is not None or e_dt is not None:
            if s_dt is None:
                s_dt = pd.Timestamp.min.floor("D")
            if e_dt is None:
                e_dt = pd.Timestamp.max.floor("D")
            parsed_ranges.append((s_dt, e_dt))

    return parsed_ranges


def process_single_csv_file(
    file_path,
    output_path,
    columns_to_keep,
    column_rename_map,
    calculated_fields,
    all_date_ranges,
    chunksize,
    write_header_ref,
    debug_func,
    progress_func,
    overall_processed_ref,
    overall_written_ref,
    peak_memory_ref,
    enable_metrics=False,
    input_date_formats=None,
    output_date_format="%m/%d/%Y",
    order_matters=False,
    multiple_dates=False,
    is_partitioned=False,
    partition_size=0
):
    if not os.path.exists(file_path):
        if debug_func:
            debug_func(f"ERROR: Input file path invalid or missing: {file_path}")
        return False

    file_headers = get_headers_from_file(file_path, order_matters=order_matters, multiple_dates=multiple_dates)
    if not file_headers or len(file_headers) < 1:
        if debug_func:
            debug_func(f"ERROR: Could not extract headers from input file: {os.path.basename(file_path)}")
        return False

    read_kwargs = {
        "chunksize": chunksize,
        "dtype": str,
        "header": 0,
        "low_memory": False,
        "on_bad_lines": "skip",
        "mangle_dupe_cols": True
    }

    strftime_out = convert_output_format_to_strftime(output_date_format)

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as in_file:
            reader = pd.read_csv(in_file, **read_kwargs)

            for chunk_idx, chunk in enumerate(reader):
                overall_processed_ref[0] += len(chunk)

                if enable_metrics:
                    current_mem = get_current_process_memory_mb()
                    if current_mem > peak_memory_ref[0]:
                        peak_memory_ref[0] = current_mem

                cleaned_columns = [str(col).strip() for col in chunk.columns]
                chunk.columns = cleaned_columns

                # Handle Partitioned Files
                if is_partitioned and partition_size > 0:
                    partitioned_chunks = []
                    num_cols = len(chunk.columns)
                    for start_c in range(0, num_cols, partition_size):
                        sub_cols = chunk.columns[start_c:start_c + partition_size]
                        sub_df = chunk[sub_cols].copy()
                        partitioned_chunks.append(sub_df)
                    if partitioned_chunks:
                        base_cols = partitioned_chunks[0].columns
                        normalized_chunks = []
                        for sc in partitioned_chunks:
                            sc.columns = base_cols[:len(sc.columns)]
                            normalized_chunks.append(sc)
                        chunk = pd.concat(normalized_chunks, ignore_index=True)

                parsed_dates = pd.Series(index=chunk.index, dtype="datetime64[ns]")

                if not input_date_formats:
                    # Fallback to first column as date string if no format provided
                    date_col = file_headers[0]
                    if date_col in chunk.columns:
                        parsed_dates = pd.to_datetime(chunk[date_col].astype(str).str.strip(), errors="coerce")
                else:
                    if len(input_date_formats) == 1:
                        fmt_str = convert_user_format_to_python(input_date_formats[0])
                        date_col = file_headers[0]
                        date_str_series = chunk[date_col].astype(str).str.strip() if date_col in chunk.columns else chunk.iloc[:, 0].astype(str).str.strip()
                        parsed_dates = pd.to_datetime(date_str_series, format=fmt_str, errors="coerce")
                    else:
                        unique_fmts = set(input_date_formats)
                        if len(unique_fmts) == 1 and len(input_date_formats) > 1:
                            fmt_str = convert_user_format_to_python(input_date_formats[0])
                            col_name = file_headers[0]
                            if col_name in chunk.columns:
                                date_str_series = chunk[col_name].astype(str).str.strip()
                                parsed_dates = pd.to_datetime(date_str_series, format=fmt_str, errors="coerce")
                        else:
                            combined_str = pd.Series("", index=chunk.index)
                            py_fmts = []
                            for idx, fmt in enumerate(input_date_formats):
                                if idx < len(file_headers):
                                    col_name = file_headers[idx]
                                    if col_name in chunk.columns:
                                        combined_str = combined_str + " " + chunk[col_name].astype(str).str.strip()
                                py_fmts.append(convert_user_format_to_python(fmt))
                            combined_str = combined_str.str.strip()
                            full_fmt_str = " ".join(py_fmts)
                            try:
                                parsed_dates = pd.to_datetime(combined_str, format=full_fmt_str, errors="coerce")
                            except Exception:
                                fmt_str = convert_user_format_to_python(input_date_formats[0])
                                col_name = file_headers[0]
                                date_str_series = chunk[col_name].astype(str).str.strip() if col_name in chunk.columns else pd.Series("", index=chunk.index)
                                parsed_dates = pd.to_datetime(date_str_series, format=fmt_str, errors="coerce")

                chunk.insert(0, "date", parsed_dates.dt.strftime(strftime_out))

                if calculated_fields:
                    for calc_name, formula in calculated_fields.items():
                        try:
                            eval_chunk = chunk.copy()
                            for col in eval_chunk.columns:
                                eval_chunk[col] = pd.to_numeric(eval_chunk[col], errors="ignore")
                            chunk[calc_name] = eval_chunk.eval(formula)
                        except Exception as calc_err:
                            if debug_func:
                                debug_func(f"WARNING: Failed to evaluate calculated field '{calc_name}': {str(calc_err)}")
                            chunk[calc_name] = ""

                valid_chunk_dates = parsed_dates.dropna()
                active_ranges_for_chunk = []

                if not valid_chunk_dates.empty and all_date_ranges:
                    chunk_min = valid_chunk_dates.min()
                    chunk_max = valid_chunk_dates.max()
                    for r_start, r_end in all_date_ranges:
                        if not (r_end < chunk_min or r_start > chunk_max):
                            active_ranges_for_chunk.append((r_start, r_end))

                if all_date_ranges:
                    if active_ranges_for_chunk:
                        valid_dates = parsed_dates.notna()
                        combined_match_mask = pd.Series(False, index=chunk.index)
                        for r_start, r_end in active_ranges_for_chunk:
                            range_mask = valid_dates & (parsed_dates >= r_start) & (parsed_dates <= r_end)
                            combined_match_mask = combined_match_mask | range_mask
                        filtered_chunk = chunk[combined_match_mask].copy()
                    else:
                        filtered_chunk = chunk.iloc[0:0].copy()
                else:
                    filtered_chunk = chunk.copy()

                existing_cols = []
                if "date" in filtered_chunk.columns:
                    existing_cols.append("date")

                if columns_to_keep:
                    for target in columns_to_keep:
                        target_clean = target.strip()
                        if target_clean in filtered_chunk.columns and target_clean not in existing_cols:
                            existing_cols.append(target_clean)

                if calculated_fields:
                    for calc_name in calculated_fields.keys():
                        if calc_name in filtered_chunk.columns and calc_name not in existing_cols:
                            existing_cols.append(calc_name)

                filtered_chunk = filtered_chunk[existing_cols]

                default_renames = {
                    "date": "TIMESTAMP_1"
                }
                final_rename_map = {**default_renames, **column_rename_map}
                filtered_chunk.rename(columns=final_rename_map, inplace=True)

                if not filtered_chunk.empty:
                    filtered_chunk.to_csv(
                        output_path,
                        mode="a",
                        header=write_header_ref[0],
                        index=False
                    )
                    write_header_ref[0] = False
                    overall_written_ref[0] += len(filtered_chunk)

                progress_func(overall_processed_ref[0], overall_written_ref[0])

        return True

    except Exception as err:
        if debug_func:
            debug_func(f"ERROR processing file {file_path}: {str(err)}")
        return False


def execute_huge_file_processing(
    file_path,
    output_path,
    target_columns="",
    column_rename_map=None,
    calculated_fields=None,
    start_date_str="",
    end_date_str="",
    chunksize=100000,
    enable_metrics=False,
    input_date_formats=None,
    output_date_format="%m/%d/%Y",
    order_matters=False,
    multiple_dates=False,
    is_partitioned=False,
    partition_size=0,
    debug_func=print,
    progress_func=lambda p, w: None
):
    start_time = time.perf_counter() if enable_metrics else 0
    initial_mem = get_current_process_memory_mb() if enable_metrics else 0.0

    if debug_func:
        debug_func("Backend execution initiated...")
        if enable_metrics:
            debug_func(f"[METRIC] Initial RAM Allocation: {initial_mem:.2f} MB")

    if column_rename_map is None:
        column_rename_map = {}
    if calculated_fields is None:
        calculated_fields = {}

    file_list = []
    if isinstance(file_path, list):
        file_list = file_path
    elif isinstance(file_path, str) and file_path.strip():
        for f in file_path.split(","):
            clean_f = f.strip()
            if clean_f:
                file_list.append(clean_f)

    if not file_list:
        if debug_func:
            debug_func("ERROR: No valid input files specified.")
        return False

    all_date_ranges = parse_date_range(start_date_str, end_date_str, debug_func)

    columns_to_keep = []
    if target_columns and target_columns.strip():
        for c in target_columns.split(","):
            clean_col = c.strip()
            if clean_col:
                columns_to_keep.append(clean_col)

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            pass
    except Exception as e:
        if debug_func:
            debug_func(f"ERROR: Cannot create output file target: {str(e)}")
        return False

    write_header_ref = [True]
    overall_processed_ref = [0]
    overall_written_ref = [0]
    peak_memory_ref = [initial_mem]

    for idx, single_file in enumerate(file_list):
        if debug_func:
            debug_func(f"Processing File [{idx + 1}/{len(file_list)}]: {os.path.basename(single_file)}")

        process_single_csv_file(
            file_path=single_file,
            output_path=output_path,
            columns_to_keep=columns_to_keep,
            column_rename_map=column_rename_map,
            calculated_fields=calculated_fields,
            all_date_ranges=all_date_ranges,
            chunksize=chunksize,
            write_header_ref=write_header_ref,
            debug_func=debug_func,
            progress_func=progress_func,
            overall_processed_ref=overall_processed_ref,
            overall_written_ref=overall_written_ref,
            peak_memory_ref=peak_memory_ref,
            enable_metrics=enable_metrics,
            input_date_formats=input_date_formats,
            output_date_format=output_date_format,
            order_matters=order_matters,
            multiple_dates=multiple_dates,
            is_partitioned=is_partitioned,
            partition_size=partition_size
        )

    elapsed_time = time.perf_counter() - start_time if enable_metrics else 0.0
    rows_per_sec = overall_processed_ref[0] / elapsed_time if (enable_metrics and elapsed_time > 0) else 0.0

    if enable_metrics and debug_func:
        debug_func("==================================================")
        debug_func("            BENCHMARK PERFORMANCE METRICS         ")
        debug_func("==================================================")
        debug_func(f"Execution Time    : {elapsed_time:.2f} seconds")
        debug_func(f"Rows Processed    : {overall_processed_ref[0]:,}")
        debug_func(f"Rows Written      : {overall_written_ref[0]:,}")
        debug_func(f"Processing Rate   : {rows_per_sec:,.0f} rows/sec")
        debug_func(f"Peak RAM Usage    : {peak_memory_ref[0]:.2f} MB")
        debug_func("==================================================")

        report_data = {
            "elapsed_time": elapsed_time,
            "rows_processed": overall_processed_ref[0],
            "rows_written": overall_written_ref[0],
            "rows_per_sec": rows_per_sec,
            "peak_memory": peak_memory_ref[0]
        }
        write_performance_report_csv("performance_report.csv", report_data)
        debug_func("[METRIC] Performance report appended to 'performance_report.csv'.")

    gc.collect()
    return overall_written_ref[0] > 0


# ---------------------------------------------------------------------------
# DIALOG WINDOWS (UNTOUCHED EULA LOGIC)
# ---------------------------------------------------------------------------

def calculate_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    if not os.path.exists(file_path):
        return ""
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


def handle_search_populate(listbox, visible_options_ref, working_set):
    listbox.delete(0, tk.END)
    for idx, option in enumerate(visible_options_ref[0]):
        listbox.insert(tk.END, option)
        if option in working_set:
            listbox.selection_set(idx)


def handle_search_filter(search_var, options, visible_options_ref, listbox, working_set):
    query = search_var.get().strip().lower()
    if not query:
        visible_options_ref[0] = list(options)
    else:
        visible_options_ref[0] = [item for item in options if query in item.lower()]
    handle_search_populate(listbox, visible_options_ref, working_set)


def handle_listbox_select(event, listbox, visible_options_ref, working_set):
    selected_indices = listbox.curselection()
    currently_selected_visible = {visible_options_ref[0][i] for i in selected_indices}
    for item in visible_options_ref[0]:
        if item in currently_selected_visible:
            working_set.add(item)
        else:
            working_set.discard(item)


def handle_select_all_visible(visible_options_ref, working_set, listbox):
    for item in visible_options_ref[0]:
        working_set.add(item)
    handle_search_populate(listbox, visible_options_ref, working_set)


def handle_clear_all(working_set, visible_options_ref, listbox):
    working_set.clear()
    handle_search_populate(listbox, visible_options_ref, working_set)


def handle_apply_selection(on_apply_callback, working_set, dialog):
    on_apply_callback(working_set)
    dialog.destroy()


def open_searchable_dialog(parent, options, selected_set, on_apply_callback, dialog_title="Select Headers"):
    dialog = tk.Toplevel(parent)
    dialog.title(dialog_title)
    dialog.geometry("400x450")
    dialog.transient(parent)
    dialog.grab_set()
    working_set = set(selected_set)
    search_frame = ttk.Frame(dialog, padding="5")
    search_frame.pack(fill=tk.X)
    ttk.Label(search_frame, text="Search Header:").pack(side=tk.LEFT, padx=(0, 5))
    search_var = tk.StringVar()
    search_entry = ttk.Entry(search_frame, textvariable=search_var)
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    list_frame = ttk.Frame(dialog, padding="5")
    list_frame.pack(fill=tk.BOTH, expand=True)
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
    listbox = tk.Listbox(
        list_frame,
        selectmode=tk.MULTIPLE,
        yscrollcommand=scrollbar.set,
        exportselection=False
    )
    scrollbar.config(command=listbox.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    visible_options = [list(options)]

    search_var.trace_add("write", lambda *args: handle_search_filter(search_var, options, visible_options, listbox, working_set))
    listbox.bind("<<ListboxSelect>>", lambda e: handle_listbox_select(e, listbox, visible_options, working_set))

    btn_frame = ttk.Frame(dialog, padding="5")
    btn_frame.pack(fill=tk.X)
    ttk.Button(btn_frame, text="Select All Visible", command=lambda: handle_select_all_visible(visible_options, working_set, listbox)).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="Clear All", command=lambda: handle_clear_all(working_set, visible_options, listbox)).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="Apply Selection", command=lambda: handle_apply_selection(on_apply_callback, working_set, dialog)).pack(side=tk.RIGHT, padx=2)
    
    handle_search_populate(listbox, visible_options, working_set)


def open_rename_dialog(parent, available_columns, current_rename_map, on_apply_callback):
    dialog = tk.Toplevel(parent)
    dialog.title("Rename Output Columns")
    dialog.geometry("500x400")
    dialog.transient(parent)
    dialog.grab_set()

    entries = {}

    header_frame = ttk.Frame(dialog, padding="5")
    header_frame.pack(fill=tk.X)

    ttk.Label(header_frame, text="Original Column Filter", font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, padx=5)
    ttk.Label(header_frame, text="Output Column Name", font=("Helvetica", 9, "bold")).pack(side=tk.RIGHT, padx=55)

    container_frame = ttk.Frame(dialog, padding="5")
    container_frame.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(container_frame)
    scrollbar = ttk.Scrollbar(container_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    if not available_columns:
        ttk.Label(scrollable_frame, text="No active column filters selected.").pack(pady=20)
    else:
        for idx, col in enumerate(available_columns):
            row_frame = ttk.Frame(scrollable_frame, padding="2")
            row_frame.pack(fill=tk.X, expand=True, pady=2)

            lbl = ttk.Label(row_frame, text=col, width=25, anchor=tk.W)
            lbl.pack(side=tk.LEFT, padx=5)

            arrow_lbl = ttk.Label(row_frame, text="➔")
            arrow_lbl.pack(side=tk.LEFT, padx=5)

            entry_var = tk.StringVar(value=current_rename_map.get(col, col))
            entry = ttk.Entry(row_frame, textvariable=entry_var, width=30)
            entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

            entries[col] = entry_var

    def reset_fields():
        for col, var in entries.items():
            var.set(col)

    def apply_and_close():
        updated_map = {}
        for col, var in entries.items():
            new_name = var.get().strip()
            if new_name and new_name != col:
                updated_map[col] = new_name
        on_apply_callback(updated_map)
        dialog.destroy()

    btn_frame = ttk.Frame(dialog, padding="5")
    btn_frame.pack(fill=tk.X)

    ttk.Button(btn_frame, text="Reset", command=reset_fields).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Apply Renames", command=apply_and_close).pack(side=tk.RIGHT, padx=5)


# ---------------------------------------------------------------------------
# MAIN APPLICATION INTERFACE
# ---------------------------------------------------------------------------

def create_application():
    root = tk.Tk()
    root.title("CSV Tool v1.2.0")
    root.after(100, lambda: check_and_prompt_eula(root, on_complete_callback=on_eula_complete))
    root.geometry("750x720")
    root.minsize(650, 600)

    state = {
        "input_rows": [],
        "debug_visible": False,
        "selected_template_headers": set(),
        "column_rename_map": {},
        "calculated_fields": {}
    }

    main_frame = ttk.Frame(root, padding="8")
    main_frame.pack(fill=tk.BOTH, expand=True)

    file_frame = ttk.LabelFrame(main_frame, text="File Options", padding="6")
    file_frame.pack(fill=tk.X, pady=2)

    inputs_container_frame = ttk.Frame(file_frame)
    inputs_container_frame.pack(fill=tk.X, expand=True)
    inputs_container_frame.columnconfigure(1, weight=1)

    output_container_frame = ttk.Frame(file_frame)
    output_container_frame.pack(fill=tk.X, expand=True, pady=(4, 0))
    output_container_frame.columnconfigure(1, weight=1)

    output_entry = ttk.Entry(output_container_frame, width=45)

    def browse_specific_input(entry_widget):
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)

            if not output_entry.get().strip():
                base, ext = os.path.splitext(path)
                suggested_output = f"{base}_processed{ext}"
                output_entry.delete(0, tk.END)
                output_entry.insert(0, suggested_output)

    def remove_input_file_field(row_data):
        if len(state["input_rows"]) <= 1:
            messagebox.showwarning("Warning", "At least one input file row must remain.")
            return

        for widget in row_data.values():
            widget.destroy()

        state["input_rows"].remove(row_data)

        for idx, row in enumerate(state["input_rows"]):
            row["label"].config(text=f"Input CSV {idx + 1}:")

    def add_input_file_field():
        row_idx = len(state["input_rows"]) + 1

        label = ttk.Label(inputs_container_frame, text=f"Input CSV {row_idx}:")
        label.grid(row=row_idx, column=0, sticky=tk.W, pady=2)

        entry = ttk.Entry(inputs_container_frame, width=45)
        entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky=tk.EW)

        browse_btn = ttk.Button(
            inputs_container_frame,
            text="Browse...",
            command=lambda e=entry: browse_specific_input(e)
        )
        browse_btn.grid(row=row_idx, column=2, padx=(0, 2), pady=2, sticky=tk.W)

        row_data = {}

        remove_btn = ttk.Button(
            inputs_container_frame,
            text="Remove",
            command=lambda: remove_input_file_field(row_data)
        )
        remove_btn.grid(row=row_idx, column=3, pady=2, sticky=tk.W)

        row_data["label"] = label
        row_data["entry"] = entry
        row_data["browse_btn"] = browse_btn
        row_data["remove_btn"] = remove_btn

        state["input_rows"].append(row_data)

    add_input_file_field()

    add_row_btn_frame = ttk.Frame(file_frame)
    add_row_btn_frame.pack(fill=tk.X, pady=(2, 6))

    ttk.Button(add_row_btn_frame, text="+ Add Input File", command=add_input_file_field).pack(side=tk.LEFT)

    ttk.Label(output_container_frame, text="Output CSV:").grid(row=0, column=0, sticky=tk.W, pady=1)
    output_entry.grid(row=0, column=1, padx=5, pady=1, sticky=tk.EW)

    def browse_output():
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if path:
            output_entry.delete(0, tk.END)
            output_entry.insert(0, path)

    ttk.Button(output_container_frame, text="Browse...", command=browse_output).grid(row=0, column=2, pady=1, sticky=tk.W)

    config_frame = ttk.LabelFrame(main_frame, text="Filtering & Column Settings", padding="6")
    config_frame.pack(fill=tk.X, pady=2)
    config_frame.columnconfigure(1, weight=1)

    ttk.Label(config_frame, text="Header Preset File:").grid(row=0, column=0, sticky=tk.W, pady=1)

    preset_container_frame = ttk.Frame(config_frame)
    preset_container_frame.grid(row=0, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    preset_path_var = tk.StringVar(value="No Preset Loaded")
    preset_path_entry = ttk.Entry(preset_container_frame, textvariable=preset_path_var, state="readonly")
    preset_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

    selected_template_headers_var = tk.StringVar(value="No Headers Selected (Click to Search/Select)")
    rename_status_var = tk.StringVar(value="No Column Renames Configured")
    
    # Template file variables
    template_file_var = tk.StringVar(value="templateFile.csv")
    order_matters_var = tk.BooleanVar(value=False)
    multiple_dates_var = tk.BooleanVar(value=False)
    is_partitioned_var = tk.BooleanVar(value=False)

    # Date formatting variables
    output_date_format_var = tk.StringVar(value="MM/DD/YYYY")
    num_fields_var = tk.StringVar(value="1")
    partition_size_var = tk.StringVar(value="10")

    input_format_entries = []

    def update_template_header_selection_display(new_selections):
        state["selected_template_headers"] = new_selections
        if not state["selected_template_headers"]:
            selected_template_headers_var.set("No Headers Selected (Click to Search/Select)")
        else:
            sorted_list = sorted(list(state["selected_template_headers"]))
            selected_template_headers_var.set(f"{len(sorted_list)} Selected: " + ", ".join(sorted_list))

    def update_column_rename_map(new_map):
        state["column_rename_map"] = new_map
        if not state["column_rename_map"]:
            rename_status_var.set("No Column Renames Configured")
        else:
            rename_status_var.set(f"{len(state['column_rename_map'])} Column(s) Mapped")

    def load_preset_file():
        path = filedialog.askopenfilename(filetypes=[("Text/CSV Files", "*.txt *.csv"), ("All Files", "*.*")])
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as pf:
                lines = [line.strip() for line in pf.readlines() if line.strip()]

            if len(lines) < 1:
                messagebox.showerror("Preset Error", "Selected preset file is empty.")
                return

            headers = [h.strip() for h in lines[0].split(",") if h.strip()]
            if not headers:
                messagebox.showerror("Preset Error", "Line 1 does not contain any valid headers.")
                return

            new_rename_map = {}
            extra_names = []
            
            if len(lines) > 1:
                renames = [r.strip() for r in lines[1].split(",")]
                for idx, h in enumerate(headers):
                    if idx < len(renames):
                        r_name = renames[idx]
                        if r_name and r_name != h:
                            new_rename_map[h] = r_name
                
                if len(renames) > len(headers):
                    extra_names = renames[len(headers):]

            new_calculated_fields = {}
            if len(lines) > 2 and extra_names:
                formula_lines = []
                for calc_line in lines[2:]:
                    if "=" in calc_line:
                        parts = calc_line.split("=", 1)
                        c_name = parts[0].strip()
                        c_formula = parts[1].strip()
                        if c_name and c_formula:
                            new_calculated_fields[c_name] = c_formula
                    else:
                        cleaned_f = calc_line.strip()
                        if cleaned_f:
                            formula_lines.append(cleaned_f)
                
                if not new_calculated_fields and formula_lines:
                    for idx, name in enumerate(extra_names):
                        if idx < len(formula_lines):
                            new_calculated_fields[name] = formula_lines[idx]

            preset_path_var.set(os.path.basename(path))
            update_column_rename_map(new_rename_map)
            state["calculated_fields"] = new_calculated_fields

            messagebox.showinfo("Preset Loaded", f"Loaded {len(headers)} header(s), {len(new_rename_map)} rename(s), and {len(new_calculated_fields)} calculated field(s).")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to read preset file: {str(e)}")

    ttk.Button(preset_container_frame, text="Apply Preset File...", command=load_preset_file).pack(side=tk.RIGHT)

    ttk.Label(config_frame, text="Target Columns to Keep:").grid(row=1, column=0, sticky=tk.W, pady=1)

    target_cols_frame = ttk.Frame(config_frame)
    target_cols_frame.grid(row=1, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    # Template file & multi-select frame
    other_target_frame = ttk.Frame(target_cols_frame)
    other_target_frame.pack(fill=tk.X, expand=True)

    tpl_file_subframe = ttk.Frame(other_target_frame)
    tpl_file_subframe.pack(fill=tk.X, expand=True, pady=(0, 2))

    ttk.Label(tpl_file_subframe, text="Template File:").pack(side=tk.LEFT, padx=(0, 5))
    tpl_entry = ttk.Entry(tpl_file_subframe, textvariable=template_file_var, width=25)
    tpl_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

    def browse_template_file():
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if path:
            template_file_var.set(path)

    ttk.Button(tpl_file_subframe, text="Browse...", command=browse_template_file).pack(side=tk.LEFT, padx=(0, 2))

    # Checkboxes frame for options
    tpl_opt_subframe = ttk.Frame(other_target_frame)
    tpl_opt_subframe.pack(fill=tk.X, expand=True, pady=(2, 2))

    order_matters_check = ttk.Checkbutton(
        tpl_opt_subframe, 
        text="Order matters for duplicates", 
        variable=order_matters_var
    )
    order_matters_check.pack(side=tk.LEFT, padx=(0, 10))

    multiple_dates_check = ttk.Checkbutton(
        tpl_opt_subframe, 
        text="Repeated date fields", 
        variable=multiple_dates_var,
        state="disabled"
    )
    multiple_dates_check.pack(side=tk.LEFT, padx=0)

    # Partitioned file options subframe
    partition_opt_subframe = ttk.Frame(other_target_frame)
    partition_opt_subframe.pack(fill=tk.X, expand=True, pady=(2, 2))

    is_partitioned_check = ttk.Checkbutton(
        partition_opt_subframe,
        text="Is file partitioned?",
        variable=is_partitioned_var
    )
    is_partitioned_check.pack(side=tk.LEFT, padx=(0, 10))

    partition_size_label = ttk.Label(partition_opt_subframe, text="Partition Size (2-50,000):")
    def validate_digits_only(char):
        if not char:
            return True
        return char.isdigit()

    vcmd_digits = root.register(validate_digits_only)
    partition_size_entry = ttk.Entry(partition_opt_subframe, textvariable=partition_size_var, width=8, validate="key", validatecommand=(vcmd_digits, "%S"))


    def on_partition_toggle(*args):
        if is_partitioned_var.get():
            partition_size_label.pack(side=tk.LEFT, padx=(5, 2))
            partition_size_entry.pack(side=tk.LEFT, padx=2)
            multiple_dates_var.set(True)
            multiple_dates_check.config(state="disabled")
        else:
            partition_size_label.pack_forget()
            partition_size_entry.pack_forget()
            multiple_dates_check.config(state="normal")

    is_partitioned_var.trace_add("write", on_partition_toggle)
    on_partition_toggle()

    tpl_select_subframe = ttk.Frame(other_target_frame)
    tpl_select_subframe.pack(fill=tk.X, expand=True, pady=(2, 0))

    selected_template_display_entry = ttk.Entry(tpl_select_subframe, textvariable=selected_template_headers_var, state="readonly")
    selected_template_display_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

    def handle_open_template_searchable_dialog():
        path = template_file_var.get().strip()
        order_matters = order_matters_var.get()
        multiple_dates = multiple_dates_var.get()
        headers = get_headers_from_file(path, order_matters=order_matters, multiple_dates=multiple_dates)
        if not headers:
            messagebox.showerror("Error", f"Could not load headers from template file:\n{path}")
            return
        open_searchable_dialog(
            root,
            headers,
            state["selected_template_headers"],
            update_template_header_selection_display,
            dialog_title="Select Template Headers"
        )

    select_template_btn = ttk.Button(tpl_select_subframe, text="Select Headers...", command=handle_open_template_searchable_dialog)
    select_template_btn.pack(side=tk.RIGHT)

    # --- Date Formatting Configuration Section ---
    ttk.Label(config_frame, text="Output Date Format:").grid(row=2, column=0, sticky=tk.W, pady=1)
    
    def validate_date_format_char(char):
        if not char:
            return True
        for c in char:
            if c.isalpha() and c.upper() not in ('M', 'D', 'Y'):
                return False
        return True

    def enforce_upper_format(var):
        val = var.get()
        new_val = val.replace('d', 'D').replace('m', 'M').replace('y', 'Y')
        if new_val != val:
            var.set(new_val)

    vcmd = root.register(validate_date_format_char)

    output_date_format_var.trace_add("write", lambda *args: enforce_upper_format(output_date_format_var))
    output_format_entry = ttk.Entry(config_frame, textvariable=output_date_format_var, validate="key", validatecommand=(vcmd, "%S"))
    output_format_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    ttk.Label(config_frame, text="Input Date Fields Count:").grid(row=3, column=0, sticky=tk.W, pady=1)

    input_fields_config_frame = ttk.Frame(config_frame)
    input_fields_config_frame.grid(row=3, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    num_fields_combo = ttk.Combobox(input_fields_config_frame, textvariable=num_fields_var, values=["1", "2", "3", "4", "5", "6", "7", "8"], width=5, state="readonly")
    num_fields_combo.pack(side=tk.LEFT, padx=(0, 5))

    input_formats_container = ttk.Frame(config_frame)
    input_formats_container.grid(row=4, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    def generate_format_inputs():
        for widget in input_formats_container.winfo_children():
            widget.destroy()
        input_format_entries.clear()

        try:
            count = int(num_fields_var.get())
        except Exception:
            count = 1

        for i in range(count):
            row_f = ttk.Frame(input_formats_container)
            row_f.pack(fill=tk.X, expand=True, pady=1)
            ttk.Label(row_f, text=f"Field {i+1} Format:", width=15).pack(side=tk.LEFT)
            ent_var = tk.StringVar(value="MM/DD/YYYY" if i==0 else "YYYY")
            ent_var.trace_add("write", lambda *args, v=ent_var: enforce_upper_format(v))
            ent = ttk.Entry(row_f, textvariable=ent_var, validate="key", validatecommand=(vcmd, "%S"))
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
            input_format_entries.append(ent_var)

    gen_formats_btn = ttk.Button(input_fields_config_frame, text="Generate Format Inputs", command=generate_format_inputs)
    gen_formats_btn.pack(side=tk.LEFT)

    generate_format_inputs()

    ttk.Label(config_frame, text="Start Date (MM/DD/YYYY):").grid(row=5, column=0, sticky=tk.W, pady=1)
    start_date_entry = ttk.Entry(config_frame)
    start_date_entry.grid(row=5, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    ttk.Label(config_frame, text="End Date (MM/DD/YYYY):").grid(row=6, column=0, sticky=tk.W, pady=1)
    end_date_entry = ttk.Entry(config_frame)
    end_date_entry.grid(row=6, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    ttk.Label(config_frame, text="Output Column Renaming:").grid(row=7, column=0, sticky=tk.W, pady=1)

    rename_frame = ttk.Frame(config_frame)
    rename_frame.grid(row=7, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

    rename_status_entry = ttk.Entry(rename_frame, textvariable=rename_status_var, state="readonly")
    rename_status_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

    def handle_open_rename_dialog():
        available_cols = sorted(list(state["selected_template_headers"]))

        if state["calculated_fields"]:
            for calc_col in state["calculated_fields"].keys():
                if calc_col not in available_cols:
                    available_cols.append(calc_col)

        if not available_cols:
            messagebox.showinfo("Rename Columns", "Please select target column filters first before configuring renames.")
            return

        open_rename_dialog(
            root,
            available_cols,
            state["column_rename_map"],
            update_column_rename_map
        )

    rename_btn = ttk.Button(rename_frame, text="Configure Renames...", command=handle_open_rename_dialog)
    rename_btn.pack(side=tk.RIGHT)

    # --- Metrics Opt-In/Opt-Out Option Frame (Off by Default) ---
    options_frame = ttk.LabelFrame(main_frame, text="Preferences & Telemetry", padding="6")
    options_frame.pack(fill=tk.X, pady=2)

    enable_metrics_var = tk.BooleanVar(value=False)
    metrics_check = ttk.Checkbutton(
        options_frame, 
        text="Enable Local Performance & Diagnostic Metrics Logging (Execution Time & RAM)", 
        variable=enable_metrics_var
    )
    metrics_check.pack(anchor=tk.W, padx=5, pady=2)

    control_frame = ttk.Frame(main_frame, padding="4")
    control_frame.pack(fill=tk.X, pady=4)

    start_button = ttk.Button(control_frame, text="Start Processing")
    start_button.pack(side=tk.LEFT, padx=5)

    debug_toggle_btn = ttk.Button(control_frame, text="Show Debug Window")
    debug_toggle_btn.pack(side=tk.LEFT, padx=5)

    status_label = ttk.Label(control_frame, text="Status: Ready")
    status_label.pack(side=tk.LEFT, padx=10)

    debug_frame = ttk.LabelFrame(main_frame, text="Debug Console Diagnostics", padding="4")
    debug_text = tk.Text(debug_frame, wrap=tk.WORD, height=8, bg="#1e1e1e", fg="#00ff00")
    debug_scrollbar = ttk.Scrollbar(debug_frame, orient=tk.VERTICAL, command=debug_text.yview)
    debug_text.configure(yscrollcommand=debug_scrollbar.set)

    def log_message(message):
        debug_text.insert(tk.END, str(message) + "\n")
        debug_text.see(tk.END)

    def update_progress(processed, written):
        status_label.config(text=f"Processed: {processed:,} rows | Written: {written:,} rows")

    def toggle_debug_window():
        if not state["debug_visible"]:
            root.geometry("750x860")
            debug_frame.pack(fill=tk.BOTH, expand=True, pady=4)
            debug_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            debug_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            debug_toggle_btn.config(text="Hide Debug Window")
            state["debug_visible"] = True
        else:
            debug_frame.pack_forget()
            root.geometry("750x720")
            debug_toggle_btn.config(text="Show Debug Window")
            state["debug_visible"] = False

    debug_toggle_btn.config(command=toggle_debug_window)

    def run_job_thread(
        file_in,
        file_out,
        target_cols,
        rename_map,
        calc_fields,
        start_dates,
        end_dates,
        enable_metrics,
        input_date_formats,
        output_date_format,
        order_matters,
        multiple_dates,
        is_partitioned,
        partition_size,
        chunk_size=100000
    ):
        try:
            log_message("Initializing background processing job...")

            success = execute_huge_file_processing(
                file_path=file_in,
                output_path=file_out,
                target_columns=target_cols,
                column_rename_map=rename_map,
                calculated_fields=calc_fields,
                start_date_str=start_dates,
                end_date_str=end_dates,
                enable_metrics=enable_metrics,
                input_date_formats=input_date_formats,
                output_date_format=output_date_format,
                order_matters=order_matters,
                multiple_dates=multiple_dates,
                is_partitioned=is_partitioned,
                partition_size=partition_size,
                chunksize=chunk_size,
                debug_func=log_message,
                progress_func=update_progress
            )

            if success:
                log_message("Job execution completed successfully.")
            else:
                log_message("Job execution finished with warnings or zero matching records.")

        except Exception as err:
            log_message(f"CRITICAL WORKER THREAD ERROR: {str(err)}")
        finally:
            root.after(0, lambda: start_button.config(state="normal"))

    def start_processing():
        file_in_list = []
        for row in state["input_rows"]:
            val = row["entry"].get().strip()
            if val:
                file_in_list.append(val)

        file_in = ",".join(file_in_list)
        file_out = output_entry.get().strip()

        target_cols = ",".join(sorted(list(state["selected_template_headers"])))
        start_dates = start_date_entry.get().strip()
        end_dates = end_date_entry.get().strip()
        enable_metrics = enable_metrics_var.get()
        output_date_format = output_date_format_var.get().strip()
        input_date_formats = [ent.get().strip() for ent in input_format_entries if ent.get().strip()]
        order_matters = order_matters_var.get()
        multiple_dates = multiple_dates_var.get()
        is_partitioned = is_partitioned_var.get()
        
        try:
            partition_size = int(partition_size_var.get().strip())
        except Exception:
            partition_size = 0

        if is_partitioned and (partition_size < 2 or partition_size > 50000):
            log_message("ERROR: Partition size must be between 2 and 50,000 columns.")
            messagebox.showerror("Error", "Partition size must be between 2 and 50,000 columns.")
            return

        if not file_in or not file_out:
            log_message("ERROR: Both input and output file paths must be selected.")
            messagebox.showerror("Error", "Please specify both input and output file paths.")
            return

        start_button.config(state="disabled")

        worker = threading.Thread(
            target=run_job_thread,
            args=(
                file_in,
                file_out,
                target_cols,
                dict(state["column_rename_map"]),
                dict(state["calculated_fields"]),
                start_dates,
                end_dates,
                enable_metrics,
                input_date_formats,
                output_date_format,
                order_matters,
                multiple_dates,
                is_partitioned,
                partition_size
            ),
            daemon=True
        )
        worker.start()

    start_button.config(command=start_processing)

    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    create_application()
