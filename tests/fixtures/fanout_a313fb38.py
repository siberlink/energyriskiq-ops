# Frozen decision function from the verified a313fb380665 ops baseline.
def fanout_alert_events_to_users() -> Dict:
    """
    Phase B: Fanout alert events to eligible users.
    
    Enforces:
    - Plan quotas (instant vs digest limits)
    - User preferences (channel enablement)
    - delivery_kind determination (instant vs digest)
    - Idempotency via unique constraint
    - User allowlist filtering (if ALERTS_SEND_ALLOWLIST_USER_IDS is set)
    
    Returns structured counts for monitoring.
    """
    from src.alerts.quota_helpers import (
        check_delivery_eligibility,
        determine_delivery_kind,
        get_user_alert_prefs,
        get_plan_quotas
    )
    
    logger.info("Phase B: Fanout alert events to eligible users...")
    
    allowlist = get_allowlisted_user_ids()
    
    alert_events = get_unsent_alert_events(lookback_hours=24)
    if not alert_events:
        logger.info("No recent alert events to fan out")
        return {
            'events_processed': 0,
            'users_considered': 0,
            'deliveries_created': 0,
            'deliveries_skipped_quota': 0,
            'deliveries_skipped_prefs': 0,
            'deliveries_skipped_missing_dest': 0,
            'allowlist_active': allowlist is not None
        }
    
    users = get_eligible_users()
    
    if allowlist:
        original_count = len(users) if users else 0
        users = [u for u in users if u['id'] in allowlist] if users else []
        logger.info(f"Allowlist filter: {original_count} -> {len(users)} users")
    
    if not users:
        logger.info("No eligible users found")
        return {
            'events_processed': len(alert_events),
            'users_considered': 0,
            'deliveries_created': 0,
            'deliveries_skipped_quota': 0,
            'deliveries_skipped_prefs': 0,
            'deliveries_skipped_missing_dest': 0
        }
    
    logger.info(f"Processing {len(alert_events)} alert events for {len(users)} users")
    
    for u in users:
        logger.info(f"Eligible user: id={u['id']}, email={u['email']}, plan={u.get('plan', 'free')}")
    
    deliveries_created = 0
    skipped_quota = 0
    skipped_prefs = 0
    skipped_missing_dest = 0
    skipped_already_exists = 0
    skipped_filter = 0
    users_considered = 0
    
    for ae in alert_events:
        alert_event_id = ae['id']
        alert_type = ae['alert_type']
        scope_region = ae['scope_region']
        scope_assets = ae['scope_assets'] or []
        
        logger.info(f"Processing alert_event {alert_event_id}: type={alert_type}, region={scope_region}")
        
        for user in users:
            user_id = user['id']
            plan = user['plan'] or 'free'
            users_considered += 1
            
            try:
                plan_settings = get_plan_settings(plan)
                allowed_types = get_allowed_alert_types(plan)
            except Exception:
                plan_settings = get_plan_settings('free')
                allowed_types = get_allowed_alert_types('free')
            
            if alert_type not in allowed_types:
                logger.info(f"User {user_id}: skipped - alert_type {alert_type} not in allowed_types {allowed_types}")
                skipped_filter += 1
                continue
            
            user_regions = get_user_regions(user_id)
            if scope_region and scope_region not in user_regions and 'global' not in user_regions:
                logger.info(f"User {user_id}: skipped - region mismatch (event={scope_region}, user={user_regions})")
                skipped_filter += 1
                continue
            
            if alert_type == 'ASSET_RISK_SPIKE' and scope_assets:
                user_assets = get_user_enabled_assets(user_id)
                if not any(a in user_assets for a in scope_assets):
                    logger.info(f"User {user_id}: skipped - asset mismatch")
                    skipped_filter += 1
                    continue
            
            user_enabled_types = get_user_enabled_alert_types(user_id)
            if alert_type not in user_enabled_types:
                logger.info(f"User {user_id}: skipped - alert_type {alert_type} not in user_enabled_types {user_enabled_types}")
                skipped_filter += 1
                continue
            
            user_prefs = get_user_alert_prefs(user_id)
            delivery_kind = determine_delivery_kind(user_prefs, plan)
            
            logger.info(f"User {user_id}: PASSED all filters for alert_event {alert_event_id}")
            
            account_id = create_delivery(user_id, alert_event_id, 'account', 'sent', delivery_kind=delivery_kind)
            if account_id:
                logger.info(f"User {user_id}: created account delivery {account_id}")
                deliveries_created += 1
            
            for channel in ['email', 'telegram', 'sms']:
                eligibility = check_delivery_eligibility(
                    user_id=user_id,
                    user=user,
                    channel=channel,
                    plan=plan,
                    alert_event_id=alert_event_id
                )
                
                if not eligibility.eligible:
                    logger.info(f"User {user_id}: {channel} not eligible - {eligibility.skip_reason}")
                    if eligibility.skip_reason == 'missing_destination':
                        skipped_missing_dest += 1
                    elif eligibility.skip_reason == 'already_exists':
                        skipped_already_exists += 1
                    elif eligibility.skip_reason in ('channel_disabled_by_user', 'sms_not_in_plan'):
                        skipped_prefs += 1
                    elif eligibility.skip_reason in ('quota_exceeded', 'plan_digest_only', 'channel_not_allowed'):
                        skipped_quota += 1
                    continue
                
                d_id = create_delivery(
                    user_id, alert_event_id, channel, 'queued',
                    delivery_kind=eligibility.delivery_kind
                )
                if d_id:
                    logger.info(f"User {user_id}: created {channel} delivery {d_id} (kind={eligibility.delivery_kind})")
                    deliveries_created += 1
                else:
                    logger.info(f"User {user_id}: failed to create {channel} delivery (already exists?)")
        
        mark_fanout_completed(alert_event_id)
    
    result = {
        'events_processed': len(alert_events),
        'users_considered': users_considered,
        'deliveries_created': deliveries_created,
        'deliveries_skipped_quota': skipped_quota,
        'deliveries_skipped_prefs': skipped_prefs,
        'deliveries_skipped_missing_dest': skipped_missing_dest,
        'deliveries_skipped_already_exists': skipped_already_exists,
        'deliveries_skipped_filter': skipped_filter,
        'allowlist_active': allowlist is not None
    }
    
    logger.info(f"Phase B complete: {deliveries_created} created, skipped: quota={skipped_quota}, prefs={skipped_prefs}, missing={skipped_missing_dest}, exists={skipped_already_exists}, filter={skipped_filter}")
    return result


