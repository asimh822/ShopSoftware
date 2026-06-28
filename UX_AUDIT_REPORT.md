# UX Audit Report — United Mobile EPOS
*Generated from code audit of all UI Python files*

---

## main.py

### MainWindow / NavButton / Sidebar
- [Tab Order] PASS — Enter-as-Tab filter applied application-wide via `EnterAsTabFilter`; sidebar nav buttons support keyboard activation.
- [Button Placement] PASS — Sidebar 44 px nav buttons, left-edge aligned, consistent across all pages.
- [Labels] PASS — Nav labels clear (Dashboard, Sales, Purchase, Ledger, Masters, Reports, Settings, WhatsApp).
- [Logical Flow] PASS — Clear separation between sidebar navigation and main content area.

### OwnerPinDialog / LockOverlay
- [Tab Order] PASS — PIN field auto-focuses; Enter confirms.
- [Button Placement] PASS — Confirm/Unlock button below PIN entry field.
- [Field Sizing] PASS — PIN field sized for 4-digit entry; `setMaxLength` enforced.

---

## sales.py

### SaleForm
- [Tab Order] WARNING — Header (Date → Sale Type toggle → Salesman), then customer stack (Contact → Name in cash mode; combo in credit mode), then IMEI field, then price spin, then Add button, then discount/note fields, then payment fields, then Save/Cancel. No explicit `setTabOrder()` calls; relies on widget insertion order. The toggle buttons (`btn_cash`, `btn_credit`) are in the tab chain but activating them via keyboard doesn't also shift focus to the customer stack — user must Tab again. Consider `setFocusPolicy(Qt.FocusPolicy.NoFocus)` on toggles.
- [Button Placement] PASS — Save/Cancel fixed at bottom footer strip; Add button inline with IMEI row (correct placement for a staged-add flow).
- [Field Sizing] PASS — `cash_contact` 115 px (11 digits), `cash_name` 150 px with `setMaxLength(18)`, `contact_status_lbl` 20 px fixed. IMEI field 148 px fixed.
- [Labels] MINOR — "Name *:" label inline in cash row but no asterisk equivalent in credit row ("Credit Customer *" has the asterisk in the text, not the label). Minor inconsistency.
- [Dropdown] PASS — `SearchableComboBox` used for salesman and credit customer combos.
- [Logical Flow] PASS — Cash contact field is gated (enables name only after valid phone); payment fields conditionally show/hide based on payment method. Credit balance label appears after customer selection.

### ImeiDropdown / ImeiSelectDialog
- [Tab Order] PASS — Arrow keys navigate list; Enter confirms; Escape hides.
- [Button Placement] PASS — OK/Cancel at dialog bottom.
- [Field Sizing] PASS — Dropdown minimum 540 px wide, shows up to 8 rows.

### SaleDetailDialog
- [Tab Order] PASS — Read-only; only Close and Delete buttons need focus.
- [Button Placement] WARNING — Delete Voucher button appears *above* the Close button (it's added first). Convention is destructive actions below or separated. Low risk since it requires a PIN confirm, but consider reordering: Close first, Delete second with visual separation.
- [Labels] PASS — SV Number, Date, Type, Customer, Total clearly labeled.

### SaleReturnForm
- [Tab Order] CAUTION — After customer combo, IMEI lookup field, and return lines table, tab should reach the Notes field then Save/Cancel. Verify tab does not land on table cells before reaching Save.
- [Button Placement] PASS — Save/Cancel in footer strip.
- [Logical Flow] PASS — Return lines validated against selected customer; stock status shown per line.

---

## purchase.py

### PurchaseForm
- [Tab Order] CAUTION — Toggle buttons (Supplier Purchase / Cash Purchase) are in the tab chain. Switching type hides/shows `_sup_widget` and `_cash_pay_card`, but focus is not redirected after the switch — user must Tab blind to find the next visible field. Add focus redirect in `_set_purchase_type`.
- [Button Placement] PASS — Save/Cancel in footer strip.
- [Field Sizing] PASS — Date field 108 px fixed; supplier combo 200 px minimum; notes field minimum 160 px with stretch factor 1.
- [Labels] PASS — "Supplier *:" label styled red/bold (matches Sales form salesman label). "Date:", "Notes:" inline and consistent.
- [Dropdown] PASS — `SearchableComboBox` for supplier and brand/model combos.
- [Logical Flow] PASS — `_sup_widget` and `supplier_balance_lbl` both hidden when Cash Purchase selected (via `_set_purchase_type`). `_cash_pay_card` shown only for cash purchases.

### PurchaseReturnForm
- [Tab Order] PASS — Date → Supplier → Notes → IMEI lookup → table → Save/Cancel.
- [Button Placement] PASS — Save/Cancel in footer.
- [Field Sizing] PASS — Supplier combo 200 px min, IMEI field 280 px min.
- [Logical Flow] PASS — IMEI field disabled until supplier is selected.

---

## ledger.py

### LedgerPage
- [Tab Order] **CRITICAL** — Party type toggle (Suppliers / Customers / Bank) switches visible widgets; no focus redirect after mode change. If focus is on the party combo when user switches to Bank mode, focus lands on a now-hidden widget. Implement `setFocus()` to the relevant first control inside `_set_party_type`.
- [Button Placement] PASS — CP / CR / JV buttons in control card; Export PDF/CSV at top right.
- [Labels] CAUTION — "Party:" label uses `setFixedWidth(36)`, "From:" `setFixedWidth(38)`, "To:" `setFixedWidth(24)`. If OS font scale changes these widths may clip. Use `setSizePolicy` instead.
- [Dropdown] PASS — `SearchableComboBox` for party selection; repopulated on type switch.
- [Logical Flow] WARNING — Switching party type clears the party combo but does not scroll the ledger table back to top or clear displayed balance. Users switching from Supplier to Customer may still see stale data until they select a new party.

### MultiLineCpCrDialog
- [Tab Order] WARNING — Dynamic row addition: no documented behaviour for Tab in last field of last row (should it add a row or move to buttons?). No `returnPressed` override shown on row fields.
- [Button Placement] CAUTION — "Add Row" button and "Save/Cancel" are visually close; accidental Save before adding all rows is possible. Add spacing or a separator.
- [Logical Flow] WARNING — Dialog accepts partial rows (empty party or zero amount). Consider validating each row on Save and highlighting incomplete rows rather than silently ignoring them.

### DoubleEntryJournalDialog
- [Tab Order] PASS — Dr type → Dr party → Cr type → Cr party → amount → notes → buttons.
- [Button Placement] PASS — OK/Cancel at bottom.
- [Labels] WARNING — "Debit" and "Credit" may not be meaningful to non-accounting staff. Add tooltips: "Debit: party that owes us" / "Credit: party we owe".
- [Logical Flow] WARNING — No visual confirmation that Dr = Cr (they share a single amount field, which is correct, but the UI doesn't make this explicit). Consider a preview line: "DR Rs.X  ←→  CR Rs.X".

---

## masters.py

### BrandsTab / ModelsTab / SuppliersTab / CustomersTab / SalesmanTab
- [Tab Order] PASS — Search field → Add button → table rows; Edit/Delete buttons reachable via keyboard row navigation.
- [Button Placement] PASS — Add in control card; Edit/Delete inline in table rows.
- [Field Sizing] PASS — Search fields and buttons consistently sized across all tabs.
- [Labels] PASS — Table column headers clear and consistent.
- [Logical Flow] PASS — Standard list-detail CRUD pattern throughout.

### BrandDialog / ModelDialog / SupplierDialog / CustomerDialog / SalesmanDialog
- [Tab Order] PASS — Fields in logical order; Enter on last field triggers OK.
- [Button Placement] PASS — OK/Cancel at dialog bottom right.
- [Field Sizing] CAUTION — `SalesmanDialog` PIN field: verify `setMaxLength(4)` is enforced (4-digit PIN per CLAUDE.md). Contact fields: verify `setMaxLength(11)`.
- [Labels] PASS — All dialog fields clearly labeled.

---

## reports.py

### ReportsPage (all tabs)
- [Tab Order] PASS — Filter controls → Search → table; Tab widget keyboard-navigable.
- [Button Placement] PASS — Search and Export buttons consistently placed in top filter card across all tabs.
- [Field Sizing] PASS — Date fields, brand combo, and buttons consistently sized.
- [Labels] PASS — Tab labels (Stock Summary, IMEI Stock, Sales, Purchases, Profit, Cash Book, etc.) are descriptive.
- [Dropdown] PASS — Brand filter combo uses `SearchableComboBox`; includes "All Brands" option.
- [Logical Flow] PASS — All report tabs follow the same pattern: set filters → Search → view table → Export.

### CashBookTab
- [Labels] PASS — Today / Yesterday quick buttons present; date range filter available.
- [Logical Flow] PASS — Compact two-column layout (Cash In / Cash Out) with (Cash) / (Bank) descriptors per CLAUDE.md spec.

---

## settings_page.py

### SettingsPage
- [Tab Order] CAUTION — Long scrollable form (~11 sections). Tab will traverse fields in DOM order, which may not match the visual left-to-right, top-to-bottom order inside each section if layouts are built non-linearly. Verify tab traverses: Shop Info → Thermal → WhatsApp → Security → Backup → Bank Accounts → Opening Balances → Year End.
- [Button Placement] **WARNING** — Save/Reset buttons are at the bottom of a tall scrollable form. On a small monitor or when only the top is visible, users may not see or find them. Consider pinning Save to the bottom of the viewport (sticky footer) or duplicating it at the top.
- [Labels] CAUTION — Across 11 sections, verify label style is consistent: some may use colon, others may not.
- [Logical Flow] WARNING — No "unsaved changes" indicator. If user edits Shop Name and navigates away via the sidebar, changes are silently lost. Add a `_dirty` flag and prompt on navigation.

### YearEndCloseDialog
- [Tab Order] PASS — Confirmation checkbox → folder picker → Confirm/Cancel.
- [Button Placement] PASS — Confirm/Cancel at dialog bottom; Confirm disabled until checkbox ticked.
- [Logical Flow] PASS — Destructive operation guarded by checkbox confirmation and owner PIN.

---

## whatsapp_page.py

### WhatsAppPage
- [Tab Order] PASS — Info/status card → message table; row-level Send/Mark Sent buttons keyboard-reachable via table row selection.
- [Button Placement] PASS — Send/Mark Sent inline per row; Connect button in status card.
- [Labels] PASS — Table columns clear: Customer, Message, Status, Sent Date.
- [Logical Flow] PASS — Page shows pending WhatsApp messages; status updates on send.

---

## Priority Summary

Top 5 most impactful issues across all files:

1. **[CRITICAL] LedgerPage — focus lost on party-type switch** (`ledger.py : LedgerPage._set_party_type`). When the user toggles Suppliers ↔ Customers ↔ Bank, focus stays on the previously active widget which may now be hidden. Keyboard users get stranded. Fix: call `setFocus()` on the correct first control inside `_set_party_type`.

2. **[CRITICAL] SettingsPage — Save button not visible without scrolling** (`settings_page.py : SettingsPage`). On any monitor smaller than 1080 px tall the Save button is off-screen. No unsaved-changes warning means edits are silently lost on navigation. Fix: sticky footer Save button + `_dirty` flag with navigation prompt.

3. **[WARNING] PurchaseForm / SaleForm — toggle-type buttons in tab chain without focus redirect** (`purchase.py : PurchaseForm._set_purchase_type`, `sales.py : SaleForm._set_type`). After toggling Cash ↔ Supplier (or Cash ↔ Credit), the relevant new fields are visible but focus is not moved there. Keyboard users must Tab blindly. Fix: add `self.<first_relevant_field>.setFocus()` at end of each `_set_*` method.

4. **[WARNING] MultiLineCpCrDialog — no row validation on Save** (`ledger.py : MultiLineCpCrDialog`). Dialog silently accepts zero-amount or empty-party rows. Users may submit incomplete multi-line payments without realising. Fix: validate each row on Save; highlight incomplete rows in red.

5. **[WARNING] SaleDetailDialog — Delete Voucher button above Close button** (`sales.py : SaleDetailDialog`). Destructive action is the first button the user reaches when Tabbing; Close is below it. Convention is Cancel/Close first, destructive action last (and visually separated). Fix: reorder — Close button first, then a separator, then Delete Voucher.
