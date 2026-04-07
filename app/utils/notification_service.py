# =========================
# CREATE NOTIFICATION
# =========================
def create_notification(
    cursor,
    org_id,
    user_id,
    role,
    title,
    message,
    reference_type=None,
    reference_id=None,
    latitude=None,
    longitude=None,
    accuracy=None
):
    cursor.execute("""
        INSERT INTO notifications
        (
            org_id,
            user_id,
            role,
            title,
            message,
            reference_type,
            reference_id,
            latitude,
            longitude,
            accuracy
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        org_id,
        user_id,
        role,
        title,
        message,
        reference_type,
        reference_id,
        latitude,
        longitude,
        accuracy
    ))


# =========================
# GET NOTIFICATIONS
# =========================
def get_notifications(cursor, user_id, role, org_id, limit=30):
    cursor.execute("""
        SELECT
            n.id,
            n.title,
            n.message,
            n.is_read,
            n.event_time,
            n.reference_type,
            n.reference_id,
            n.latitude,
            n.longitude,
            n.accuracy
        FROM notifications n
        WHERE n.user_id = %s
          AND n.role = %s
          AND n.org_id = %s
        ORDER BY n.event_time DESC
        LIMIT %s
    """, (user_id, role, org_id, limit))

    return cursor.fetchall()


# =========================
# MARK ALL AS READ
# =========================
def mark_all_as_read(cursor, user_id, role, org_id):
    cursor.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE user_id = %s
          AND role = %s
          AND org_id = %s
          AND is_read = 0
    """, (user_id, role, org_id))


# =========================
# UNREAD COUNT
# =========================
def get_unread_count(cursor, user_id, role, org_id):
    cursor.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE user_id = %s
          AND role = %s
          AND org_id = %s
          AND is_read = 0
    """, (user_id, role, org_id))

    return cursor.fetchone()[0]
