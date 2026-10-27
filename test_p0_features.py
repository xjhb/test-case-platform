import requests, json, sys

BASE = 'http://127.0.0.1:8000/api'
results = []

def test(name, passed, detail=''):
    status = 'PASS' if passed else 'FAIL'
    results.append((name, status, detail))
    icon = 'PASS' if passed else 'FAIL'
    print(f'  [{icon}] {name}: {detail}' if detail else f'  [{icon}] {name}')

# 0. Login
print('=== 0. Login ===')
r = requests.post(f'{BASE}/auth/login', json={'username': 'admin', 'password': 'admin123'})
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}
test('Login', r.status_code == 200, f'status={r.status_code}')

projects = requests.get(f'{BASE}/projects', headers=headers).json()
project_id = projects[0]['id'] if projects else None
test('Get projects', project_id is not None, f'found {len(projects)} projects')

# Find a project with plans
plan_id = None
plan_project_id = None
for p in projects:
    plans = requests.get(f'{BASE}/plans', headers=headers, params={'project_id': p['id']}).json()
    if plans:
        plan_id = plans[0]['id']
        plan_project_id = p['id']
        break
test('Get plans', plan_id is not None, f'plan_id={plan_id} in project {plan_project_id}')

print()
print('=== 1. Defect Management ===')

r = requests.post(f'{BASE}/defects', headers=headers, json={
    'title': 'Test Defect - Login Bug',
    'description': 'No error message when wrong password',
    'severity': '严重',
    'priority': 'P1',
    'project_id': project_id,
})
test('Create defect', r.status_code == 200, f'defect_id={r.json().get("id")}')
defect_id = r.json()['id']

r = requests.get(f'{BASE}/defects', headers=headers)
data = r.json()
test('List defects', r.status_code == 200 and 'total' in data, f'total={data.get("total")}')

r = requests.get(f'{BASE}/defects/{defect_id}', headers=headers)
test('Get defect detail', r.status_code == 200 and r.json()['id'] == defect_id)

r = requests.put(f'{BASE}/defects/{defect_id}', headers=headers, json={'status': '处理中', 'assignee_id': 1})
test('Update status to processing', r.status_code == 200 and r.json()['status'] == '处理中')

r = requests.put(f'{BASE}/defects/{defect_id}', headers=headers, json={'status': '已修复'})
test('Update status to fixed', r.status_code == 200 and r.json()['status'] == '已修复' and r.json().get('resolved_at') is not None)

r = requests.put(f'{BASE}/defects/{defect_id}', headers=headers, json={'status': '关闭'})
test('Update status to closed', r.status_code == 200 and r.json()['status'] == '关闭' and r.json().get('closed_at') is not None)

r = requests.post(f'{BASE}/defects', headers=headers, json={
    'title': 'Test Defect 2 - Slow Page',
    'description': 'Page loads over 3 seconds',
    'severity': '一般',
    'priority': 'P2',
    'project_id': project_id,
})
defect_id2 = r.json()['id']
test('Create 2nd defect', r.status_code == 200)

r = requests.get(f'{BASE}/defects', headers=headers, params={'severity': '严重'})
test('Filter by severity', r.status_code == 200 and all(d['severity'] == '严重' for d in r.json()['items']))

r = requests.get(f'{BASE}/defects', headers=headers, params={'keyword': 'Login'})
test('Search by keyword', r.status_code == 200 and len(r.json()['items']) >= 1)

r = requests.get(f'{BASE}/defects/stats/summary', headers=headers, params={'project_id': project_id})
test('Defect stats', r.status_code == 200 and 'total' in r.json(), f'total={r.json().get("total")}')

r = requests.put(f'{BASE}/defects/{defect_id2}', headers=headers, json={'status': 'INVALID'})
test('Reject invalid status', r.status_code == 400)

r = requests.post(f'{BASE}/defects', headers=headers, json={
    'title': 'bad', 'severity': 'NOTEXIST', 'priority': 'P1', 'project_id': project_id,
})
test('Reject invalid severity', r.status_code == 400)

r = requests.delete(f'{BASE}/defects/{defect_id2}', headers=headers)
test('Delete defect', r.status_code == 200)

r = requests.get(f'{BASE}/defects/{defect_id2}', headers=headers)
test('Confirm deleted', r.status_code == 404)

print()
print('=== 2. Test Case Version History ===')

r = requests.get(f'{BASE}/testcases', headers=headers, params={'project_id': project_id})
cases = r.json().get('items', [])
test('Get test cases', r.status_code == 200, f'found {len(cases)} cases')

# Create a new test case (will get v1 automatically)
r = requests.post(f'{BASE}/testcases', headers=headers, json={
    'project_id': project_id,
    'module': 'Test Module',
    'title': 'Version Test Case',
    'precondition': 'None',
    'steps': 'Step 1',
    'expected': 'Pass',
    'priority': 'P1',
})
testcase_id = r.json()['id'] if r.status_code == 200 else None
test('Create test case for version test', testcase_id is not None, f'testcase_id={testcase_id}')

if testcase_id:
    r = requests.get(f'{BASE}/testcases/{testcase_id}/versions', headers=headers)
    versions = r.json()
    test('Initial version exists (v1)', len(versions) >= 1, f'{len(versions)} versions')

    r = requests.put(f'{BASE}/testcases/{testcase_id}', headers=headers, json={
        'title': 'Version Test Case - Modified',
    })
    test('Edit test case', r.status_code == 200)

    r = requests.get(f'{BASE}/testcases/{testcase_id}/versions', headers=headers)
    versions_after = r.json()
    test('New version created after edit', len(versions_after) > len(versions), f'{len(versions)} -> {len(versions_after)}')

    latest_version = versions_after[0]
    r = requests.get(f'{BASE}/testcases/{testcase_id}/versions/{latest_version["id"]}', headers=headers)
    test('Get version detail', r.status_code == 200 and r.json()['version'] == latest_version['version'])

    first_version = versions_after[-1]
    r = requests.post(f'{BASE}/testcases/{testcase_id}/versions/{first_version["id"]}/rollback', headers=headers)
    test('Rollback to version', r.status_code == 200)

    r = requests.get(f'{BASE}/testcases/{testcase_id}/versions', headers=headers)
    versions_rollback = r.json()
    test('Version count increased after rollback', len(versions_rollback) > len(versions_after), f'{len(versions_after)} -> {len(versions_rollback)}')

    # Cleanup
    r = requests.delete(f'{BASE}/testcases/{testcase_id}', headers=headers)
    test('Cleanup version test case', r.status_code == 200)

print()
print('=== 3. Test Report Auto-Generation ===')

if plan_id:
    r = requests.post(f'{BASE}/reports/generate', headers=headers, params={'plan_id': plan_id, 'stage': 'SIT'})
    test('Generate report', r.status_code == 200, f'report_id={r.json().get("id")}')
    report_id = r.json()['id']

    r = requests.get(f'{BASE}/reports/list', headers=headers)
    test('List reports', r.status_code == 200 and len(r.json()) >= 1)

    r = requests.get(f'{BASE}/reports/list', headers=headers, params={'plan_id': plan_id})
    test('Filter reports by plan', r.status_code == 200 and all(rp['plan_id'] == plan_id for rp in r.json()))

    r = requests.get(f'{BASE}/reports/{report_id}', headers=headers)
    test('Get report detail', r.status_code == 200 and r.json()['id'] == report_id)

    detail = r.json()
    has_stats = all(k in detail for k in ['total_cases', 'passed_cases', 'failed_cases', 'pass_rate', 'defect_count'])
    test('Report has statistics', has_stats)

    r = requests.get(f'{BASE}/reports/{report_id}/export', headers=headers)
    test('Export report Excel', r.status_code == 200 and 'spreadsheetml' in r.headers.get('content-type', ''))

    r = requests.post(f'{BASE}/reports/generate', headers=headers, params={'plan_id': plan_id, 'stage': 'SIT'})
    test('Regenerate report (overwrite)', r.status_code == 200 and r.json()['id'] == report_id)

    r = requests.post(f'{BASE}/reports/generate', headers=headers, params={'plan_id': plan_id, 'stage': 'UAT'})
    test('Generate UAT report', r.status_code == 200)

    r = requests.post(f'{BASE}/reports/generate', headers=headers, params={'plan_id': plan_id, 'stage': 'INVALID'})
    test('Reject invalid stage', r.status_code == 400)

    r = requests.delete(f'{BASE}/reports/{report_id}', headers=headers)
    test('Delete report', r.status_code == 200)

print()
print('=== 4. Notification System ===')

r = requests.get(f'{BASE}/notifications', headers=headers)
test('Get notification list', r.status_code == 200)

r = requests.get(f'{BASE}/notifications/unread-count', headers=headers)
test('Get unread count', r.status_code == 200 and 'count' in r.json(), f'count={r.json().get("count")}')

# Create a test user for notification
r = requests.post(f'{BASE}/auth/register', headers=headers, json={
    'username': 'testuser_notify',
    'password': 'test123456',
    'display_name': 'Test User Notify',
})
test_user_id = None
if r.status_code == 200:
    test_user_id = r.json().get('id')
    test('Create test user for notification', True, f'user_id={test_user_id}')
else:
    users = requests.get(f'{BASE}/users', headers=headers).json()
    for u in users:
        if u['username'] == 'testuser_notify':
            test_user_id = u['id']
            break
    test('Create test user for notification', test_user_id is not None, f'user_id={test_user_id}')

r = requests.post(f'{BASE}/defects', headers=headers, json={
    'title': 'Notification Test Defect',
    'description': 'Test assignee notification',
    'severity': '一般',
    'priority': 'P2',
    'project_id': project_id,
    'assignee_id': test_user_id,
})
notify_defect_id = r.json()['id']
test('Create defect with assignee', r.status_code == 200)

# Login as the assigned user to check their notifications
r = requests.post(f'{BASE}/auth/login', json={'username': 'testuser_notify', 'password': 'test123456'})
if r.status_code == 200:
    test_headers = {'Authorization': f'Bearer {r.json()["access_token"]}'}
    r = requests.get(f'{BASE}/notifications', headers=test_headers)
    notifications = r.json() if isinstance(r.json(), list) else r.json().get('items', [])
    has_defect_notification = any(n['type'] == 'defect_assigned' for n in notifications)
    test('Assign triggers notification (for assignee)', has_defect_notification)

    r = requests.post(f'{BASE}/notifications/mark-read', headers=test_headers, json={'ids': []})
    test('Mark all read (as assignee)', r.status_code == 200)

    r = requests.get(f'{BASE}/notifications/unread-count', headers=test_headers)
    test('Unread count is zero (as assignee)', r.status_code == 200 and r.json()['count'] == 0)

    if notifications:
        nid = notifications[0]['id']
        r = requests.delete(f'{BASE}/notifications/{nid}', headers=test_headers)
        test('Delete notification (as assignee)', r.status_code == 200)
else:
    test('Assign triggers notification', False, 'Could not login as test user')
    test('Mark all read', False, 'Skipped')
    test('Unread count is zero', False, 'Skipped')

r = requests.delete(f'{BASE}/defects/{notify_defect_id}', headers=headers)
test('Cleanup notify defect', r.status_code == 200)

r = requests.delete(f'{BASE}/defects/{defect_id}', headers=headers)
test('Cleanup test defect', r.status_code == 200)

print()
print('=' * 60)
passed = sum(1 for _, s, _ in results if s == 'PASS')
failed = sum(1 for _, s, _ in results if s == 'FAIL')
total = len(results)
print(f'Total: {total} tests, {passed} passed, {failed} failed')
if failed:
    print('Failed tests:')
    for name, status, detail in results:
        if status == 'FAIL':
            print(f'  FAIL: {name}: {detail}')
print(f'Pass rate: {passed/total*100:.1f}%')
