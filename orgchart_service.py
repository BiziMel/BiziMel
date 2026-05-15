def get_or_create_org_chart(connection, account_id):
    chart = connection.execute(
        "SELECT * FROM org_charts WHERE account_id = ? ORDER BY id LIMIT 1",
        (account_id,),
    ).fetchone()
    if chart:
        return chart
    cursor = connection.execute(
        "INSERT INTO org_charts (account_id, layout_prefs) VALUES (?, ?)",
        (account_id, "{}"),
    )
    return connection.execute(
        "SELECT * FROM org_charts WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()


def get_org_nodes(connection, org_chart_id):
    return connection.execute(
        """
        SELECT *
        FROM org_chart_nodes
        WHERE org_chart_id = ?
        ORDER BY COALESCE(parent_contact_id, 0), sort_index, contact_id
        """,
        (org_chart_id,),
    ).fetchall()


def node_dicts(nodes):
    return [dict(node) for node in nodes]


def validate_no_cycles(nodes, moved_contact_id, new_parent_contact_id):
    if not new_parent_contact_id:
        return True
    moved_contact_id = int(moved_contact_id)
    new_parent_contact_id = int(new_parent_contact_id)
    if moved_contact_id == new_parent_contact_id:
        raise ValueError("A contact cannot report to themselves.")

    children_by_parent = {}
    for node in node_dicts(nodes):
        parent = node.get("parent_contact_id")
        if parent is not None:
            children_by_parent.setdefault(int(parent), []).append(int(node["contact_id"]))

    stack = list(children_by_parent.get(moved_contact_id, []))
    descendants = set()
    while stack:
        child_id = stack.pop()
        if child_id in descendants:
            continue
        descendants.add(child_id)
        stack.extend(children_by_parent.get(child_id, []))
    if new_parent_contact_id in descendants:
        raise ValueError("That move would create a reporting loop.")
    return True


def sibling_nodes(connection, org_chart_id, parent_contact_id):
    if parent_contact_id is None:
        return connection.execute(
            """
            SELECT *
            FROM org_chart_nodes
            WHERE org_chart_id = ?
              AND parent_contact_id IS NULL
            ORDER BY sort_index, contact_id
            """,
            (org_chart_id,),
        ).fetchall()
    return connection.execute(
        """
        SELECT *
        FROM org_chart_nodes
        WHERE org_chart_id = ?
          AND parent_contact_id = ?
        ORDER BY sort_index, contact_id
        """,
        (org_chart_id, parent_contact_id),
    ).fetchall()


def renumber_siblings(connection, org_chart_id, parent_contact_id, preferred_contact_id=None, preferred_index=None):
    siblings = [dict(row) for row in sibling_nodes(connection, org_chart_id, parent_contact_id)]
    if preferred_contact_id is not None:
        preferred_contact_id = int(preferred_contact_id)
        moving = [node for node in siblings if int(node["contact_id"]) == preferred_contact_id]
        siblings = [node for node in siblings if int(node["contact_id"]) != preferred_contact_id]
        if moving:
            insert_at = preferred_index if preferred_index is not None else len(siblings)
            insert_at = max(0, min(int(insert_at), len(siblings)))
            siblings.insert(insert_at, moving[0])
    for index, node in enumerate(siblings):
        connection.execute(
            """
            UPDATE org_chart_nodes
            SET sort_index = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE org_chart_id = ?
              AND contact_id = ?
            """,
            (index, org_chart_id, node["contact_id"]),
        )


def upsert_node(connection, org_chart_id, contact_id, parent_contact_id, sort_index=0):
    existing = connection.execute(
        """
        SELECT *
        FROM org_chart_nodes
        WHERE org_chart_id = ?
          AND contact_id = ?
        """,
        (org_chart_id, contact_id),
    ).fetchone()
    if existing:
        connection.execute(
            """
            UPDATE org_chart_nodes
            SET parent_contact_id = ?,
                sort_index = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE org_chart_id = ?
              AND contact_id = ?
            """,
            (parent_contact_id, sort_index, org_chart_id, contact_id),
        )
    else:
        connection.execute(
            """
            INSERT INTO org_chart_nodes (
                org_chart_id,
                contact_id,
                parent_contact_id,
                sort_index
            )
            VALUES (?, ?, ?, ?)
            """,
            (org_chart_id, contact_id, parent_contact_id, sort_index),
        )
    renumber_siblings(connection, org_chart_id, parent_contact_id, contact_id, sort_index)


def delete_node(connection, org_chart_id, contact_id, mode):
    node = connection.execute(
        """
        SELECT *
        FROM org_chart_nodes
        WHERE org_chart_id = ?
          AND contact_id = ?
        """,
        (org_chart_id, contact_id),
    ).fetchone()
    if not node:
        return

    if mode == "delete_subtree":
        nodes = get_org_nodes(connection, org_chart_id)
        children_by_parent = {}
        for row in nodes:
            parent = row["parent_contact_id"]
            if parent is not None:
                children_by_parent.setdefault(parent, []).append(row["contact_id"])
        to_delete = {contact_id}
        stack = list(children_by_parent.get(contact_id, []))
        while stack:
            child_id = stack.pop()
            if child_id in to_delete:
                continue
            to_delete.add(child_id)
            stack.extend(children_by_parent.get(child_id, []))
        placeholders = ",".join("?" for _ in to_delete)
        connection.execute(
            f"DELETE FROM org_chart_nodes WHERE org_chart_id = ? AND contact_id IN ({placeholders})",
            tuple([org_chart_id, *to_delete]),
        )
        renumber_siblings(connection, org_chart_id, node["parent_contact_id"])
        return

    children = sibling_nodes(connection, org_chart_id, contact_id)
    for child in children:
        connection.execute(
            """
            UPDATE org_chart_nodes
            SET parent_contact_id = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE org_chart_id = ?
              AND contact_id = ?
            """,
            (node["parent_contact_id"], org_chart_id, child["contact_id"]),
        )
    connection.execute(
        "DELETE FROM org_chart_nodes WHERE org_chart_id = ? AND contact_id = ?",
        (org_chart_id, contact_id),
    )
    renumber_siblings(connection, org_chart_id, node["parent_contact_id"])


def ordered_insert_index(siblings, target_contact_id, placement):
    target_contact_id = int(target_contact_id)
    for index, node in enumerate(siblings):
        if int(node["contact_id"]) == target_contact_id:
            return index if placement == "peerLeft" else index + 1
    return len(siblings)
