"""User-interface strings: English and Traditional Chinese (Taiwan) here;
Simplified Chinese (China) in lang_zh_cn.py and Japanese in lang_ja.py."""

LANGS = [("en", "English"), ("zh_TW", "繁體中文"), ("zh_CN", "简体中文"), ("ja", "日本語")]
_lang = "en"

S = {
    "app_title": ("Duplicate Image Finder", "重複圖片搜尋器"),
    "folders": ("Folders to scan", "要掃描的資料夾"),
    "add_folder": ("Add folders…", "新增資料夾…"),
    "add_folders_title": ("Select folders to scan", "選擇要掃描的資料夾"),
    "add_folder_tip": ("Select one or more folders (hold Ctrl or Shift to pick several).\nYou can also drag folders onto the list.",
                       "選擇一個或多個資料夾（按住 Ctrl 或 Shift 可多選）。\n也可以直接把資料夾拖曳到清單中。"),
    "remove_folder": ("Remove", "移除"),
    "remove_folders": ("Remove {n} folders", "移除 {n} 個資料夾"),
    "remove_folder_tip": ("Remove the selected folders from the list (Delete key).\nCtrl+click or Shift+click to select several.",
                          "從清單移除選取的資料夾（Delete 鍵）。\nCtrl+點選或 Shift+點選可選取多個。"),
    "drop_hint": ("Add folders with the button or drag them here", "按按鈕或將資料夾拖曳到此處"),
    "options": ("Options", "選項"),
    "subfolders": ("Include subfolders for newly added folders", "新增的資料夾預設包含子資料夾"),
    "col_subfolders": ("Subfolders", "子資料夾"),
    "subfolders_tip": ("Ticked = also scan every folder inside this one. Unticked = only this folder.",
                       "打勾 = 一併掃描其中所有子資料夾。未打勾 = 只掃描此資料夾。"),
    "col_select": ("Select", "選取"),
    "all_tip": ("Select: tick to mark EVERY file in the list, including the best copies. Untick to clear all.\n"
                "To mark only the duplicates, use Select > Mark all duplicates (Ctrl+A).",
                "選取：打勾即標記清單中「所有」檔案（包含最佳的一份）。取消打勾則全部清除。\n"
                "若只要標記重複檔案，請使用「選取 > 標記所有重複檔案」（Ctrl+A）。"),
    "detect_crops": ("Detect cropped copies (AI)", "偵測裁切過的圖片（AI）"),
    "sniff": ("Find misnamed images", "找出副檔名錯誤的圖片"),
    "sniff_tip": ("Also open files without an image extension and check their content (slower).",
                  "同時檢查沒有圖片副檔名的檔案內容（較慢）。"),
    "similarity": ("Visual similarity", "視覺相似度"),
    "similarity_tip": ("Resized / recompressed / converted copies above this similarity are duplicates.",
                       "縮放、重新壓縮或轉檔後的圖片，相似度高於此值即視為重複。"),
    "crop_sim": ("Crop match", "裁切比對"),
    "crop_sim_tip": ("Lower finds smaller crops but checks more pairs (slower).",
                     "數值越低可找到越小的裁切，但需比對更多組合（較慢）。"),
    "device": ("Device", "運算裝置"),
    "device_auto": ("Auto (GPU if available)", "自動（優先使用 GPU）"),
    "device_cpu": ("CPU only", "僅使用 CPU"),
    "language": ("Language", "語言"),
    "theme": ("Theme", "主題"),
    "a_columns": ("Columns", "欄位"),
    "a_reset_columns": ("Reset columns", "重設欄位"),
    "theme_system": ("Use Windows setting", "跟隨 Windows 設定"),
    "theme_light": ("Light", "淺色"),
    "theme_dark": ("Dark", "深色"),
    "apply_done_nolog": ("Done: {ok} succeeded, {fail} failed.", "完成：成功 {ok} 個，失敗 {fail} 個。"),
    "scan": ("Scan", "開始掃描"),
    "cancel": ("Cancel", "取消"),
    "clear_cache": ("Clear cache", "清除快取"),
    "clear_cache_q": ("Delete the saved analysis of all files? The next scan will re-read every image.\n"
                      "Groups you hid as \"not duplicates\" will be shown again.",
                      "要刪除所有檔案的分析快取嗎？下次掃描將重新讀取每張圖片。\n"
                      "先前標示為「非重複」而隱藏的群組也會再次顯示。"),
    # results
    "col_remove": ("Remove", "移除"),
    "remove_tip": ("Ticked = marked for REMOVE.  Unticked = KEEP.", "打勾 = 標記為「移除」。未打勾 = 保留。"),
    "group_tip": ("Tick to mark every duplicate in this group (the best copy is kept). Untick to keep all.",
                  "打勾即標記此組所有重複檔案（保留最佳的一份）。取消打勾則全部保留。"),
    "legend": ("☑ ticked = REMOVE    ☐ unticked = KEEP    ★ = best quality    "
               "Tick a group row to mark all its duplicates.",
               "☑ 打勾 = 移除    ☐ 未打勾 = 保留    ★ = 最佳品質    在群組列打勾可標記該組所有重複檔案。"),
    "col_name": ("Name", "名稱"),
    "col_match": ("Match", "比對結果"),
    "col_res": ("Resolution", "解析度"),
    "col_size": ("Size", "檔案大小"),
    "col_date": ("Date modified", "修改日期"),
    "col_fmt": ("Format", "格式"),
    "col_folder": ("Folder", "資料夾"),
    "group_n": ("Group {n} · {count} files", "第 {n} 組 · {count} 個檔案"),
    "preview_group": ("{name} · frees {size}", "{name} · 可釋放 {size}"),
    "reclaim": ("{size} to free", "可釋放 {size}"),
    "kind_keep": ("★ Best", "★ 最佳"),
    "kind_exact": ("Exact copy", "完全相同"),
    "kind_similar": ("Similar {p}%", "相似 {p}%"),
    "kind_cropped": ("Cropped {p}%", "裁切 {p}%"),
    "kind_variant": ("Exception", "例外"),
    "tag_keep": ("KEEP", "保留"),
    "tag_remove": ("REMOVE", "移除"),
    "preview": ("Preview", "預覽"),
    "preview_hint": ("Select a group to preview it. Double-click an image to enlarge.",
                     "選擇群組即可預覽，按兩下圖片可放大。"),
    "keep_this": ("Keep this one only", "只保留這張"),
    "toggle": ("Toggle keep / remove", "切換保留／移除"),
    "open_file": ("Open", "開啟"),
    "prev_tip": ("Previous (←)", "上一張（←）"),
    "next_tip": ("Next (→)", "下一張（→）"),
    "open_default": ("Open (default viewer)", "開啟（預設檢視器）"),
    "open_default_tip": ("Open the image in the app Windows uses for this file type",
                         "以 Windows 為此檔案類型設定的預設程式開啟圖片"),
    "show_folder": ("Show in folder", "在資料夾中顯示"),
    # actions
    "action_box": ("What to do with files marked REMOVE", "標記為「移除」的檔案要如何處理"),
    "act_move": ("Move to folder:", "移動到資料夾："),
    "act_recycle": ("Send to Recycle Bin", "移到資源回收筒"),
    "act_delete": ("Delete permanently", "永久刪除"),
    "browse": ("Browse…", "瀏覽…"),
    "apply": ("Apply", "執行"),
    "summary": ("{n} files marked · {size}", "已標記 {n} 個檔案 · {size}"),
    # status
    "ready": ("Ready", "就緒"),
    "detecting_device": ("Detecting GPU…", "正在偵測 GPU…"),
    "stage_enumerate": ("Collecting files… {done}", "正在收集檔案… {done}"),
    "stage_model": ("Loading AI model (first run downloads ~90 MB)…", "正在載入 AI 模型（首次執行會下載約 90 MB）…"),
    "stage_cache": ("Reading cache… {done}/{total}", "正在讀取快取… {done}/{total}"),
    "stage_analyze": ("Analyzing images… {done}/{total}", "正在分析圖片… {done}/{total}"),
    "stage_exact": ("Finding exact copies… {done}/{total}", "正在尋找完全相同的檔案… {done}/{total}"),
    "stage_visual": ("Comparing images… {done}/{total}", "正在比對圖片… {done}/{total}"),
    "stage_features": ("Comparing AI features… {done}/{total}", "正在比對 AI 特徵… {done}/{total}"),
    "stage_verify": ("Verifying cropped matches… {done}/{total}", "正在驗證裁切比對… {done}/{total}"),
    "stage_group": ("Grouping…", "正在分組…"),
    "done_status": ("{groups} groups, {dups} duplicates in {files} files ({sec} s)",
                    "共 {files} 個檔案中找到 {groups} 組、{dups} 個重複（{sec} 秒）"),
    "cancelled": ("Scan canceled. Finished work is cached; the next scan continues from there.",
                  "已取消掃描。已完成的部分已快取，下次掃描會接續進行。"),
    "errors_btn": ("Skipped files: {n}", "略過的檔案：{n}"),
    "errors_title": ("Files that could not be read", "無法讀取的檔案"),
    "warnings": ("Warnings", "警告"),
    "cpu_warn": ("No GPU found – running on CPU. Large scans with crop detection will be slower.",
                 "未偵測到 GPU，將使用 CPU 運算。大量檔案並偵測裁切時速度會較慢。"),
    # dialogs
    "no_folders": ("Please add at least one folder to scan.", "請至少新增一個要掃描的資料夾。"),
    "no_dest": ("Please choose a destination folder for moved files.", "請選擇移動檔案的目的資料夾。"),
    "nothing_marked": ("No files are marked REMOVE.", "沒有標記為「移除」的檔案。"),
    "confirm_title": ("Confirm", "確認"),
    "confirm_move": ("Move {n} files ({size}) to:\n{dest}?", "要將 {n} 個檔案（{size}）移動到：\n{dest}？"),
    "confirm_recycle": ("Send {n} files ({size}) to the Recycle Bin?", "要將 {n} 個檔案（{size}）移到資源回收筒嗎？"),
    "confirm_delete": ("PERMANENTLY delete {n} files ({size})?\nThis cannot be undone.",
                       "要「永久刪除」{n} 個檔案（{size}）嗎？\n此動作無法復原。"),
    "skipped_groups": ("{n} groups had every file marked REMOVE; they were skipped so one copy is always kept.\n"
                       "(Moving to a folder is allowed for whole groups, because nothing is lost.)",
                       "有 {n} 組的所有檔案都被標記為「移除」，為確保至少保留一份已略過這些組。\n"
                       "（若選擇「移動到資料夾」則可整組移動，因為檔案不會遺失。）"),
    "applying": ("Processing files… {done}/{total}", "正在處理檔案… {done}/{total}"),
    # short, overall status for the bottom status bar
    "short_enumerate": ("Scanning · Collecting files…", "掃描中 · 收集檔案…"),
    "short_model": ("Scanning · Loading AI model…", "掃描中 · 載入 AI 模型…"),
    "short_cache": ("Scanning · Reading cache…", "掃描中 · 讀取快取…"),
    "short_analyze": ("Scanning · Analyzing…", "掃描中 · 分析中…"),
    "short_exact": ("Scanning · Finding exact copies…", "掃描中 · 尋找完全相同的檔案…"),
    "short_visual": ("Scanning · Comparing…", "掃描中 · 比對中…"),
    "short_features": ("Scanning · Comparing AI features…", "掃描中 · 比對 AI 特徵…"),
    "short_verify": ("Scanning · Verifying crops…", "掃描中 · 驗證裁切…"),
    "short_group": ("Scanning · Grouping…", "掃描中 · 分組…"),
    "scan_busy": ("Scanning · Stage {n}/{total}: {what}", "掃描中 · 階段 {n}/{total}：{what}"),
    "eta": ("about {t} left", "約剩 {t}"),
    "sname_enumerate": ("Collecting files…", "收集檔案…"),
    "sname_cache": ("Reading cache…", "讀取快取…"),
    "sname_model": ("Loading AI model…", "載入 AI 模型…"),
    "sname_analyze": ("Analyzing…", "分析中…"),
    "sname_exact": ("Finding exact copies…", "尋找完全相同的檔案…"),
    "sname_visual": ("Comparing…", "比對中…"),
    "sname_features": ("Comparing AI features…", "比對 AI 特徵…"),
    "sname_verify": ("Verifying crops…", "驗證裁切…"),
    "sname_group": ("Grouping…", "分組…"),
    "short_move": ("Moving files…", "正在移動檔案…"),
    "apply_done_short": ("Done: {ok} succeeded, {fail} failed.", "完成：成功 {ok} 個，失敗 {fail} 個。"),
    "short_recycle": ("Sending files to the Recycle Bin…", "正在移到資源回收筒…"),
    "short_delete": ("Deleting files…", "正在刪除檔案…"),
    "apply_done": ("Done: {ok} succeeded, {fail} failed.\nLog: {log}", "完成：成功 {ok} 個，失敗 {fail} 個。\n紀錄檔：{log}"),
    "dest_inside": ("The destination folder is inside a scanned folder; it will be excluded from future scans.",
                    "目的資料夾位於掃描的資料夾內，之後掃描時會自動排除。"),
    "about": ("About", "關於"),
    "formats": ("Supported formats", "支援的格式"),
    "close": ("Close", "關閉"),
    "zoom_fit": ("Fit", "符合視窗"),
    "viewer_hint": ("← → previous/next  ·  wheel or Ctrl +/− zoom  ·  Ctrl 0 fit  ·  drag to pan  ·  double-click 100%/fit",
                    "← → 上一張／下一張  ·  滾輪或 Ctrl +/− 縮放  ·  Ctrl 0 符合視窗  ·  拖曳移動  ·  按兩下 100%／符合"),
    "prev": ("◀ Previous", "◀ 上一張"),
    "next": ("Next ▶", "下一張 ▶"),
    "scan_failed": ("Scan failed:\n{err}", "掃描失敗：\n{err}"),
    # menus
    "m_file": ("&File", "檔案(&F)"),
    "m_edit": ("&Select", "選取(&S)"),
    "m_view": ("&View", "檢視(&V)"),
    "m_settings": ("Se&ttings", "設定(&T)"),
    "m_about": ("&About", "關於(&A)"),
    "a_export": ("Export results to CSV…", "匯出結果為 CSV…"),
    "a_save_progress": ("Save progress", "儲存進度"),
    "a_load_progress": ("Load progress", "載入進度"),
    "a_export_scan": ("Export scan…", "匯出掃描結果…"),
    "a_import_scan": ("Import scan…", "匯入掃描結果…"),
    "scan_filter": ("Saved scans (*.xml *.difscan)", "掃描結果檔 (*.xml *.difscan)"),
    "scan_filter_xml": ("Saved scan (*.xml)", "掃描結果檔 (*.xml)"),
    "nothing_to_save": ("There are no results to save yet. Scan first.", "目前沒有可儲存的結果，請先掃描。"),
    "save_failed": ("Could not save:\n{err}", "無法儲存：\n{err}"),
    "progress_saved": ("Progress saved for these folders ({n} groups, with your selections). "
                       "File > Load progress restores it.",
                       "已儲存這些資料夾的進度（{n} 個群組及目前的選取）。可用「檔案 > 載入進度」還原。"),
    "scan_exported": ("Scan exported to {path}", "已匯出掃描結果至 {path}"),
    "no_progress": ("There is no saved progress for the folders in the list.\n\n"
                    "Use File > Save progress after a scan, or File > Import scan… to open a saved file.",
                    "清單中的資料夾沒有已儲存的進度。\n\n"
                    "請在掃描後使用「檔案 > 儲存進度」，或使用「檔案 > 匯入掃描結果…」開啟已儲存的檔案。"),
    "scan_file_bad": ("Could not open this scan file:\n{err}", "無法開啟此掃描檔：\n{err}"),
    "replace_results_q": ("Replace the current results with the saved scan?\n\nTicks you changed since your "
                          "last save will be lost.",
                          "要以已儲存的掃描結果取代目前的結果嗎？\n\n上次儲存後變更的勾選將會遺失。"),
    "ld_intro": ("Some things changed since this scan was saved ({saved}):",
                 "此掃描結果儲存（{saved}）後有些內容已變更："),
    "ld_missing_folders": ("• Folders not found:\n{list}", "• 找不到下列資料夾：\n{list}"),
    "ld_missing_files": ("• Files no longer found: {n} (left out).", "• {n} 個檔案已不存在，將不列出。"),
    "ld_changed_files": ("• Files modified since: {n}. They are listed but set to KEEP, so nothing is "
                         "removed based on an old comparison. Scan again to compare them.",
                         "• {n} 個檔案在儲存後已修改。仍會列出但設為保留，避免依舊的比對結果誤刪。請重新掃描以重新比對。"),
    "ld_dropped_groups": ("• Groups with no duplicates left: {n} (left out).",
                          "• {n} 個群組已沒有重複檔案，將不列出。"),
    "ld_folders_replaced": ("• The folder list will be replaced with this scan's folders:\n{list}",
                            "• 資料夾清單將改為此掃描的資料夾：\n{list}"),
    "ld_continue": ("Load it anyway?", "仍要載入嗎？"),
    "ld_empty": ("Nothing is left to show: none of the duplicates in this saved scan still exist.",
                 "沒有可顯示的內容：此掃描結果中的重複檔案都已不存在。"),
    "loaded_status": ("Loaded saved scan: {groups} groups (saved {saved})", "已載入掃描結果：{groups} 個群組（儲存於 {saved}）"),
    "a_open_logs": ("Open log folder", "開啟紀錄資料夾"),
    "a_exit": ("Exit", "結束"),
    "a_sel_all": ("Mark all duplicates (keep best)", "標記所有重複檔案（保留最佳）"),
    "a_sel_exact": ("Mark exact copies only", "只標記完全相同的檔案"),
    "a_sel_similar": ("Mark similar copies only", "只標記相似的檔案"),
    "a_sel_cropped": ("Mark cropped copies only", "只標記裁切的檔案"),
    "a_invert": ("Invert marks", "反轉標記"),
    "a_group_mark": ("Mark this group's duplicates", "標記此組的重複檔案"),
    "a_group_unmark": ("Unmark this group", "取消標記此組"),
    "a_expand": ("Expand all groups", "展開所有群組"),
    "a_collapse": ("Collapse all groups", "收合所有群組"),
    "a_preview": ("Show preview panel", "顯示預覽面板"),
    "a_thumbs": ("Thumbnail size", "縮圖大小"),
    "thumb_s": ("Small", "小"),
    "thumb_m": ("Medium", "中"),
    "thumb_l": ("Large", "大"),
    "a_choose_dest": ("Choose move folder…", "選擇移動目的資料夾…"),
    "a_open_data": ("Open cache folder", "開啟快取資料夾"),
    "a_reset": ("Reset all settings…", "重設所有設定…"),
    "reset_q": ("Reset all settings to defaults? (The cache is kept.)", "要將所有設定恢復預設值嗎？（快取會保留）"),
    "a_about": ("About Duplicate Image Finder", "關於重複圖片搜尋器"),
    "about_text": ("<b>Duplicate Image Finder {ver}</b><br><br>Finds exact, resized, re-encoded and cropped "
                   "duplicate images.<br><br>Created by Ben, with Claude (Anthropic).<br><a href='{url}'>{url}</a><br><a href='mailto:{mail}'>{mail}</a><br><br>"
                   "Device: {dev}<br>Supported formats: {n}<br>Settings &amp; cache: {data}<br>Logs: {logs}<br><br>MIT License",
                   "<b>重複圖片搜尋器 {ver}</b><br><br>可找出完全相同、縮放、重新編碼及裁切過的重複圖片。<br><br>"
                   "作者：Ben，與 Claude（Anthropic）共同開發。<br><a href='{url}'>{url}</a><br><a href='mailto:{mail}'>{mail}</a><br><br>"
                   "運算裝置：{dev}<br>支援格式：{n} 種<br>設定與快取：{data}<br>紀錄檔：{logs}<br><br>MIT 授權"),
    "a_sel_variants": ("Mark duplicates and exceptions", "標記重複檔案及例外"),
    "var_title": ("Exceptions", "例外規則"),
    "var_help": (
        "<b>What exceptions do</b><br>"
        "Some images look alike but are <i>not</i> duplicates, e.g. the pages of one post "
        "(12345678_p0, 12345678_p1 …) or a numbered series (image_01, image_02 …). Files caught by an "
        "exception rule stay in the list (purple “Exception” label) but are <b>not ticked automatically</b>. "
        "Use one rule or both; <b>either rule is enough</b>.<br><br>"
        "<b>Rule 1 — Name patterns</b> (not case-sensitive)<br>"
        "&nbsp;&nbsp;<code>*</code> = any text &nbsp;&nbsp;&nbsp; <code>#</code> = the number that changes<br>"
        "&nbsp;&nbsp;Separate patterns with a comma <code>,</code> &nbsp;e.g. <code>*_p#, IMG_#, *_v#</code><br>"
        "&nbsp;&nbsp;<code>*_p#</code> → 12345678_p0, 12345678_p1 (Pixiv style) &nbsp;·&nbsp; "
        "<code>*_#</code> → scan_01, scan_02 &nbsp;·&nbsp; <code>*-#</code> → page-3, page-4<br>"
        "&nbsp;&nbsp;<code>* #</code> → Wallpaper 1, Wallpaper 2 &nbsp;·&nbsp; <code>IMG_#</code> → IMG_0012, "
        "IMG_0013 &nbsp;·&nbsp; <code>*_v#</code> → logo_v1, logo_v2<br>"
        "&nbsp;&nbsp;Advanced: start a pattern with <code>re:</code> for a regular expression (no commas); "
        "name the number group <code>(?P&lt;num&gt;\\d+)</code>.<br><br>"
        "<b>Rule 2 — Same beginning of name</b><br>"
        "&nbsp;&nbsp;Files whose first <b>N</b> characters are identical are kept. With N = 4, "
        "<code>image_01</code> and <code>image_02</code> both start with <code>imag</code>.<br>"
        "&nbsp;&nbsp;Only files the scan already matched are affected. A small N keeps a lot "
        "(N = 4 would keep every <code>IMG_…</code> photo) — prefer a distinctive length.<br><br>"
        "<b>Always treated as duplicates</b> (safety, overrides both rules): byte-identical copies, Windows "
        "copies such as “photo (1)” or “photo - Copy”, and the same name in another format "
        "(image_01.png / image_01.jpg).<br>"
        "Changes apply to the current results immediately (marks are reset).",
        "<b>例外的用途</b><br>"
        "有些圖片看起來相似但<i>並非</i>重複，例如同一篇作品的多張圖（12345678_p0、12345678_p1 …）"
        "或編號系列（image_01、image_02 …）。符合例外規則的檔案仍會顯示在清單中（紫色「例外」標籤），"
        "但<b>不會自動打勾</b>。可使用其中一條或兩條規則，<b>符合任一條即可</b>。<br><br>"
        "<b>規則 1 — 檔名規則</b>（不分大小寫）<br>"
        "&nbsp;&nbsp;<code>*</code> = 任意文字 &nbsp;&nbsp;&nbsp; <code>#</code> = 會變動的編號<br>"
        "&nbsp;&nbsp;多條規則請以逗號 <code>,</code> 分隔 &nbsp;例如 <code>*_p#, IMG_#, *_v#</code><br>"
        "&nbsp;&nbsp;<code>*_p#</code> → 12345678_p0、12345678_p1（Pixiv 格式）&nbsp;·&nbsp; "
        "<code>*_#</code> → scan_01、scan_02 &nbsp;·&nbsp; <code>*-#</code> → page-3、page-4<br>"
        "&nbsp;&nbsp;<code>* #</code> → Wallpaper 1、Wallpaper 2 &nbsp;·&nbsp; <code>IMG_#</code> → IMG_0012、"
        "IMG_0013 &nbsp;·&nbsp; <code>*_v#</code> → logo_v1、logo_v2<br>"
        "&nbsp;&nbsp;進階：以 <code>re:</code> 開頭可使用正規表示式（不可含逗號），編號群組請命名為 "
        "<code>(?P&lt;num&gt;\\d+)</code>。<br><br>"
        "<b>規則 2 — 檔名開頭相同</b><br>"
        "&nbsp;&nbsp;檔名前 <b>N</b> 個字元相同的檔案會被保留。N = 4 時，"
        "<code>image_01</code> 與 <code>image_02</code> 都以 <code>imag</code> 開頭。<br>"
        "&nbsp;&nbsp;只影響掃描已比對出的檔案。N 越小保留越多（N = 4 會保留所有 <code>IMG_…</code> 照片），"
        "建議使用較有辨識度的長度。<br><br>"
        "<b>一律視為重複</b>（安全規則，優先於兩條規則）：位元完全相同的檔案、Windows 複本如「photo (1)」或"
        "「photo - 複製」，以及相同檔名的不同格式（image_01.png / image_01.jpg）。<br>"
        "修改後會立即套用到目前的結果（標記會重設）。"),
    "var_rule1": ("Rule 1 — Name patterns (comma-separated):", "規則 1 — 檔名規則（以逗號分隔）："),
    "var_rule2": ("Rule 2 — Same beginning of name: first", "規則 2 — 檔名開頭相同：前"),
    "var_rule2_suffix": ("characters", "個字元"),
    "var_rule2_hint": ("e.g. files starting with “{start}” are kept as exceptions ({n} characters)",
                       "例如以「{start}」開頭的檔案會被保留為例外（{n} 個字元）"),
    "var_placeholder": ("e.g. *_p#, IMG_#, *_v#", "例如 *_p#, IMG_#, *_v#"),
    "var_res_none": ("→ no exception (normal duplicate rules)", "→ 不是例外（依一般重複規則）"),
    "var_res_safety": ("→ duplicate: same name (other format or Windows copy) — safety rule",
                       "→ 重複：相同檔名（不同格式或 Windows 複本）— 安全規則"),
    "var_res_pattern": ("→ exception by Rule 1 (pattern “{p}”): kept, not ticked",
                        "→ 符合規則 1（規則「{p}」）：保留，不打勾"),
    "var_res_prefix": ("→ exception by Rule 2 (same first {n} characters): kept, not ticked",
                       "→ 符合規則 2（前 {n} 個字元相同）：保留，不打勾"),
    "kind_exc_pattern": ("Exception · pattern", "例外 · 檔名規則"),
    "kind_exc_prefix": ("Exception · first {n}", "例外 · 前 {n} 字"),
    "btn_variants": ("Exceptions…", "例外…"),
    "btn_clear": ("Clear results", "清除結果"),
    "title_files": ("Files", "檔案"),
    "title_preview": ("Preview", "預覽"),
    "stats_none": ("No results yet — choose folders and press Scan.", "尚無結果 — 請選擇資料夾後按「開始掃描」。"),
    "stats_row": ("{groups} groups · {dups} duplicate files", "{groups} 組 · {dups} 個重複檔案"),
    "stats_exc": (" · {n} exceptions", " · {n} 個例外"),
    "btn_unhide": ("Show hidden ({n})", "顯示已隱藏（{n}）"),
    "unhide_q": ("Show the {n} hidden groups again?\n\nYou kept every file in these groups earlier, so they were "
                 "hidden as \"not duplicates\". They will be listed again now and in future scans.",
                 "要再次顯示 {n} 個已隱藏的群組嗎？\n\n這些群組先前所有檔案都被保留，因此被視為「非重複」而隱藏。"
                 "現在及之後的掃描都會再次列出它們。"),
    "unhide_done": ("{n} hidden groups are shown again.", "已重新顯示 {n} 個隱藏的群組。"),
    "stats_hidden": (" · {n} hidden (kept earlier)", " · 已隱藏 {n} 組（先前已保留）"),
    "hide_note": ("{n} groups where every file is KEEP will be remembered as \"not duplicates\" and hidden "
                  "from future scans (until a file changes or the cache is cleared).",
                  "所有檔案皆為「保留」的 {n} 組將被記為「非重複」，之後掃描不再顯示"
                  "（直到檔案變更或清除快取）。"),
    "confirm_hide_only": ("No files are marked REMOVE.\n\nHide the {n} groups where every file is KEEP from "
                          "future scans? (They show again if a file changes or the cache is cleared.)",
                          "沒有標記為「移除」的檔案。\n\n要將所有檔案皆為「保留」的 {n} 組從之後的掃描中隱藏嗎？"
                          "（檔案變更或清除快取後會再次顯示。）"),
    "hidden_done": ("{n} groups hidden from future scans (Settings > Clear cache shows them again).",
                    "已隱藏 {n} 組，之後掃描不再顯示（設定 > 清除快取 可再次顯示）。"),
    "a_logging": ("Enable logging (this session only)", "啟用記錄（僅限本次執行）"),
    "log_on": ("Logging to {path}", "記錄檔：{path}"),
    "log_off": ("Logging stopped.", "已停止記錄。"),
    "btn_clear_tip": ("Clear the results list, all marks and the preview. Your folders and settings are kept; "
                      "scanning again is fast thanks to the cache.",
                      "清除結果清單、所有標記及預覽。資料夾與設定會保留；因有快取，重新掃描會很快。"),
    "btn_variants_tip": ("Exceptions: look-alike files that are not duplicates (e.g. 12345678_p0, _p1) are kept, not ticked.",
                         "例外：看起來相似但不是重複的檔案（如 12345678_p0、_p1）會保留，不會自動打勾。"),
    "var_test": ("Try two file names:", "測試兩個檔名："),
    "var_invalid": ("Invalid patterns (ignored): {lines}", "無效的規則（將忽略）：{lines}"),
    "export_done": ("Exported {n} rows to:\n{path}", "已匯出 {n} 筆資料至：\n{path}"),
    "no_results": ("There are no results yet. Run a scan first.", "目前沒有結果，請先執行掃描。"),
}


def set_lang(lang):
    global _lang
    _lang = lang if lang in {code for code, _ in LANGS} else "en"


def get_lang():
    return _lang


def tr(key, **kw):
    pair = S.get(key)
    if pair is None:
        return key
    if _lang == "zh_TW":
        s = pair[1]
    elif _lang in _EXTRA:
        s = _extra(_lang).get(key, pair[0])      # missing translation: English
    else:
        s = pair[0]
    return s.format(**kw) if kw else s


_EXTRA = {"zh_CN": "lang_zh_cn", "ja": "lang_ja"}
_loaded = {}


def _extra(lang):
    if lang not in _loaded:
        import importlib
        _loaded[lang] = importlib.import_module(f"{__package__}.{_EXTRA[lang]}").T
    return _loaded[lang]


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
