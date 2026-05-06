document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-bulk-action-bar]").forEach((bar) => {
        const formId = bar.dataset.bulkActionBar;
        const countNode = bar.querySelector("[data-bulk-selected-count]");
        const checkboxes = Array.from(document.querySelectorAll(`input[type="checkbox"][form="${formId}"]`));

        const updateBar = () => {
            const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
            bar.hidden = selectedCount === 0;
            if (countNode) {
                countNode.textContent = selectedCount;
            }
        };

        checkboxes.forEach((checkbox) => {
            checkbox.addEventListener("change", updateBar);
        });

        updateBar();
    });
});
