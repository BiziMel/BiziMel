(() => {
    const SORT_ASC = "asc";
    const SORT_DESC = "desc";

    function normaliseText(value) {
        return (value || "").replace(/\s+/g, " ").trim();
    }

    function parseSortableValue(value) {
        const text = normaliseText(value);
        if (!text) {
            return { type: "empty", value: "" };
        }

        const numericText = text.replace(/[\u00a3$\u20ac,]/g, "").replace(/%$/, "").trim();
        if (/^-?\d+(\.\d+)?$/.test(numericText)) {
            return { type: "number", value: Number(numericText) };
        }

        const dateValue = Date.parse(text);
        if (!Number.isNaN(dateValue) && /\d{1,4}[-/ ]\d{1,2}|\d{1,2}[-/ ]\w+|\w+ \d{1,2}/.test(text)) {
            return { type: "date", value: dateValue };
        }

        return { type: "text", value: text.toLowerCase() };
    }

    function compareValues(left, right, direction) {
        const a = parseSortableValue(left);
        const b = parseSortableValue(right);
        const multiplier = direction === SORT_ASC ? 1 : -1;

        if (a.type === "empty" && b.type !== "empty") return 1;
        if (b.type === "empty" && a.type !== "empty") return -1;

        if (a.type === b.type && a.value < b.value) return -1 * multiplier;
        if (a.type === b.type && a.value > b.value) return 1 * multiplier;

        const leftText = normaliseText(left).toLowerCase();
        const rightText = normaliseText(right).toLowerCase();
        if (leftText < rightText) return -1 * multiplier;
        if (leftText > rightText) return 1 * multiplier;
        return 0;
    }

    function cellText(row, columnIndex) {
        const cell = row.children[columnIndex];
        return cell ? cell.innerText || cell.textContent || "" : "";
    }

    function sortTable(table, columnIndex, header) {
        const tbody = table.tBodies[0];
        if (!tbody) return;

        const currentDirection = header.dataset.sortDirection === SORT_ASC ? SORT_DESC : SORT_ASC;
        const rows = Array.from(tbody.rows).map((row, index) => ({ row, index }));

        rows.sort((left, right) => {
            const comparison = compareValues(cellText(left.row, columnIndex), cellText(right.row, columnIndex), currentDirection);
            return comparison || left.index - right.index;
        });

        rows.forEach(({ row }) => tbody.appendChild(row));

        table.querySelectorAll("th.sortable-heading").forEach((th) => {
            th.dataset.sortDirection = "";
            th.setAttribute("aria-sort", "none");
        });

        header.dataset.sortDirection = currentDirection;
        header.setAttribute("aria-sort", currentDirection === SORT_ASC ? "ascending" : "descending");
    }

    function makeTableSortable(table) {
        if (table.dataset.sortReady === "true") return;
        if (table.classList.contains("no-sort")) return;

        const headerRow = table.tHead ? table.tHead.rows[0] : table.querySelector("tr");
        const tbody = table.tBodies[0];
        if (!headerRow || !tbody || !tbody.rows.length) return;

        Array.from(headerRow.cells).forEach((header, columnIndex) => {
            if (header.colSpan && header.colSpan > 1) return;
            if (!normaliseText(header.textContent)) return;

            header.classList.add("sortable-heading");
            header.tabIndex = 0;
            header.setAttribute("role", "button");
            header.setAttribute("aria-sort", "none");
            header.title = "Sort this table";

            const activate = () => sortTable(table, columnIndex, header);
            header.addEventListener("click", activate);
            header.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    activate();
                }
            });
        });

        table.dataset.sortReady = "true";
    }

    function initialiseSortableTables() {
        document.querySelectorAll("table").forEach(makeTableSortable);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiseSortableTables);
    } else {
        initialiseSortableTables();
    }
})();
