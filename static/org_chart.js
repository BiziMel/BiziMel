(function () {
    const workspace = document.querySelector(".orgchart-workspace");
    if (!workspace) return;

    const accountId = workspace.dataset.accountId;
    const canvas = document.getElementById("orgchartCanvas");
    const contactList = document.getElementById("orgchartContactList");
    const searchInput = document.getElementById("orgchartContactSearch");
    const legend = document.getElementById("orgchartLegend");
    const saveState = document.getElementById("orgchartSaveState");
    const errorBox = document.getElementById("orgchartError");
    let state = JSON.parse(workspace.dataset.initial || "{}");
    let dragged = null;

    function setSaveState(text) {
        if (saveState) saveState.textContent = text;
    }

    function showError(message) {
        if (!errorBox) return;
        errorBox.textContent = message || "";
        errorBox.hidden = !message;
    }

    function contactById(contactId) {
        return (state.contacts || []).find((contact) => Number(contact.id) === Number(contactId));
    }

    function colourForContactType(type) {
        const palette = {
            "Champion": "#1f9d55",
            "Coach": "#2f80ed",
            "Influencer": "#9b51e0",
            "Executive Buyer": "#f2994a",
            "Executive Assistant": "#00a8a8",
            "Detractor": "#d64545",
            "Executive": "#f2994a",
            "Business": "#7cb342",
            "Technical": "#2d9cdb",
            "Procurement": "#8e6f3e",
            "Security": "#6d5dfc",
            "Project/Programme Management": "#607d8b",
            "Unclassified": "#9ca3af"
        };
        return palette[type || "Unclassified"] || "#9ca3af";
    }

    function applyContactTypeStyle(element, contact) {
        const contactType = contact.contact_type || "Unclassified";
        element.style.setProperty("--orgchart-contact-type-colour", colourForContactType(contactType));
        element.dataset.contactType = contactType;
        element.title = `${contact.name || "Unknown contact"} - ${contactType}`;
    }

    function nodeByContact(contactId) {
        return (state.nodes || []).find((node) => Number(node.contact_id) === Number(contactId));
    }

    function childrenFor(parentContactId) {
        return (state.nodes || [])
            .filter((node) => {
                if (parentContactId === null || parentContactId === undefined) {
                    return node.parent_contact_id === null || node.parent_contact_id === undefined;
                }
                return Number(node.parent_contact_id) === Number(parentContactId);
            })
            .sort((left, right) => {
                const sortDiff = Number(left.sort_index || 0) - Number(right.sort_index || 0);
                return sortDiff || Number(left.contact_id) - Number(right.contact_id);
            });
    }

    function contactsNotOnChart() {
        const chartContactIds = new Set((state.nodes || []).map((node) => Number(node.contact_id)));
        const query = (searchInput?.value || "").trim().toLowerCase();
        return (state.contacts || []).filter((contact) => {
            if (chartContactIds.has(Number(contact.id))) return false;
            const text = `${contact.name || ""} ${contact.job_title || ""} ${contact.org_dept || ""}`.toLowerCase();
            return !query || text.includes(query);
        });
    }

    function dragPayload(contactId) {
        return { contactId: Number(contactId) };
    }

    function attachDrag(element, contactId) {
        element.draggable = true;
        element.addEventListener("dragstart", (event) => {
            dragged = dragPayload(contactId);
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("application/json", JSON.stringify(dragged));
        });
    }

    function renderPalette() {
        contactList.innerHTML = "";
        const contacts = contactsNotOnChart();
        if (!contacts.length) {
            const empty = document.createElement("div");
            empty.className = "empty-state compact-empty-state";
            empty.textContent = "All matching contacts are already in the chart.";
            contactList.appendChild(empty);
            return;
        }
        contacts.forEach((contact) => {
            const tile = document.createElement("div");
            tile.className = "orgchart-contact-tile";
            tile.dataset.contactId = contact.id;
            applyContactTypeStyle(tile, contact);
            tile.innerHTML = `<span class="orgchart-photo orgchart-palette-photo"></span><strong></strong><span></span>`;
            if (contact.photo) {
                const image = document.createElement("img");
                image.src = contact.photo;
                image.alt = contact.name || "Contact photo";
                tile.querySelector(".orgchart-photo").appendChild(image);
            }
            tile.querySelector("strong").textContent = contact.name || "Unknown contact";
            tile.querySelector("span").textContent = `${contact.job_title || "Job title not set"} | ${contact.contact_type || "Unclassified"}`;
            attachDrag(tile, contact.id);
            contactList.appendChild(tile);
        });
    }

    function renderLegend() {
        if (!legend) return;
        legend.innerHTML = "";
        const contactTypes = Array.from(new Set(
            (state.contacts || []).map((contact) => contact.contact_type || "Unclassified")
        )).sort((left, right) => left.localeCompare(right));
        if (!contactTypes.length) {
            legend.hidden = true;
            return;
        }
        legend.hidden = false;
        contactTypes.forEach((contactType) => {
            const item = document.createElement("span");
            item.className = "orgchart-legend-item";
            item.innerHTML = `<span class="orgchart-legend-swatch"></span><span></span>`;
            item.querySelector(".orgchart-legend-swatch").style.backgroundColor = colourForContactType(contactType);
            item.querySelector("span:last-child").textContent = contactType;
            legend.appendChild(item);
        });
    }

    function placementFromCardEdge(event, element) {
        const rect = element.getBoundingClientRect();
        const distances = [
            { placement: "manager", value: Math.abs(event.clientY - rect.top) },
            { placement: "employee", value: Math.abs(rect.bottom - event.clientY) },
            { placement: "peerLeft", value: Math.abs(event.clientX - rect.left) },
            { placement: "peerRight", value: Math.abs(rect.right - event.clientX) }
        ];
        distances.sort((left, right) => left.value - right.value);
        return distances[0].placement;
    }

    function attachCardDrop(element, targetContactId) {
        element.addEventListener("dragover", (event) => {
            event.preventDefault();
            element.classList.add("drop-target-active");
            event.dataTransfer.dropEffect = "move";
        });
        element.addEventListener("dragleave", (event) => {
            if (!element.contains(event.relatedTarget)) {
                element.classList.remove("drop-target-active");
            }
        });
        element.addEventListener("drop", (event) => {
            event.preventDefault();
            event.stopPropagation();
            element.classList.remove("drop-target-active");
            const payload = dragged || JSON.parse(event.dataTransfer.getData("application/json") || "{}");
            if (!payload.contactId || Number(payload.contactId) === Number(targetContactId)) return;
            saveOperation({
                operation: nodeByContact(payload.contactId) ? "move" : "add",
                contact_id: payload.contactId,
                target_contact_id: targetContactId,
                placement: placementFromCardEdge(event, element)
            });
        });
    }

    function deleteButton(contactId) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "orgchart-delete-node";
        button.textContent = "x";
        button.addEventListener("click", () => {
            const hasChildren = childrenFor(contactId).length > 0;
            let mode = "promote_children";
            if (hasChildren && confirm("Delete this person and everyone below them? Select OK to delete the subtree, or Cancel to promote their direct reports.")) {
                mode = "delete_subtree";
            }
            saveOperation({ operation: "delete", contact_id: contactId, mode });
        });
        return button;
    }

    function renderNode(node) {
        const contact = contactById(node.contact_id);
        if (!contact) return document.createTextNode("");
        const li = document.createElement("li");
        li.className = "orgchart-node";
        li.dataset.contactId = contact.id;

        const card = document.createElement("div");
        card.className = "orgchart-card";
        applyContactTypeStyle(card, contact);
        attachDrag(card, contact.id);
        attachCardDrop(card, contact.id);

        const body = document.createElement("div");
        body.className = "orgchart-card-body";
        body.innerHTML = `<span class="orgchart-photo"></span><strong></strong><span></span>`;
        if (contact.photo) {
            const image = document.createElement("img");
            image.src = contact.photo;
            image.alt = contact.name || "Contact photo";
            body.querySelector(".orgchart-photo").appendChild(image);
        }
        body.querySelector("strong").textContent = contact.name || "Unknown contact";
        body.querySelector("span:last-child").textContent = `${contact.job_title || "Job title not set"} | ${contact.contact_type || "Unclassified"}`;

        card.appendChild(deleteButton(contact.id));
        card.appendChild(body);
        li.appendChild(card);

        const children = childrenFor(contact.id);
        if (children.length) {
            li.classList.add("has-children");
            const childList = document.createElement("ul");
            childList.className = "orgchart-children";
            children.forEach((child) => childList.appendChild(renderNode(child)));
            li.appendChild(childList);
        }
        return li;
    }

    function renderChart() {
        canvas.innerHTML = "";
        const roots = childrenFor(null);
        if (!roots.length) {
            const empty = document.createElement("div");
            empty.className = "orgchart-empty-canvas";
            empty.textContent = "Drop a contact here to start the org chart.";
            canvas.appendChild(empty);
        } else {
            const tree = document.createElement("ul");
            tree.className = "orgchart-tree";
            roots.forEach((node) => tree.appendChild(renderNode(node)));
            canvas.appendChild(tree);
        }
    }

    canvas.addEventListener("dragover", (event) => {
        if (event.target.closest(".orgchart-card")) return;
        event.preventDefault();
        canvas.classList.add("active");
    });
    canvas.addEventListener("dragleave", () => canvas.classList.remove("active"));
    canvas.addEventListener("drop", (event) => {
        if (event.target.closest(".orgchart-card")) return;
        event.preventDefault();
        canvas.classList.remove("active");
        const payload = dragged || JSON.parse(event.dataTransfer.getData("application/json") || "{}");
        if (!payload.contactId) return;
        saveOperation({
            operation: nodeByContact(payload.contactId) ? "move" : "add",
            contact_id: payload.contactId,
            target_contact_id: null,
            placement: "root"
        });
    });

    async function saveOperation(payload) {
        showError("");
        setSaveState("Saving...");
        try {
            const response = await fetch(`/api/accounts/${accountId}/orgchart/nodes`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Org chart save failed.");
            state = data;
            render();
            setSaveState("Saved");
        } catch (error) {
            showError(error.message);
            setSaveState("Save failed");
        }
    }

    function render() {
        renderLegend();
        renderPalette();
        renderChart();
    }

    searchInput?.addEventListener("input", renderPalette);
    document.getElementById("orgchartReset")?.addEventListener("click", render);
    document.getElementById("orgchartFit")?.addEventListener("click", () => canvas.scrollIntoView({ block: "nearest", inline: "nearest" }));
    render();
})();
