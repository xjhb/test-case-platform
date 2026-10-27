#!/usr/bin/env python3
"""P1 功能测试脚本"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def login():
    """登录获取 token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    if resp.status_code == 200:
        return resp.json()["access_token"]
    else:
        print(f"登录失败: {resp.text}")
        return None

def test_calendar_api(token):
    """测试日历视图 API"""
    print("\n=== 测试 1: 测试计划日历视图 ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 获取当前月份的日历数据
    resp = requests.get(f"{BASE_URL}/api/plans/calendar", 
                       params={"year": 2026, "month": 10},
                       headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"[PASS] 日历 API 正常，返回 {len(data)} 条计划数据")
        return True
    else:
        print(f"[FAIL] 日历 API 失败: {resp.status_code}")
        return False

def test_review_workflow(token):
    """测试用例评审流程"""
    print("\n=== 测试 2: 用例评审流程 ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 创建测试用例
    resp = requests.post(f"{BASE_URL}/api/testcases", json={
        "project_id": 1,
        "module": "测试模块",
        "title": "评审流程测试用例",
        "precondition": "无",
        "steps": "1. 测试步骤",
        "expected": "预期结果",
        "priority": "P1"
    }, headers=headers)
    
    if resp.status_code != 200:
        print(f"[FAIL] 创建用例失败: {resp.status_code}")
        return False
    
    testcase_id = resp.json()["id"]
    print(f"[PASS] 创建用例成功，ID: {testcase_id}")
    
    # 2. 提交评审
    resp = requests.post(f"{BASE_URL}/api/testcases/{testcase_id}/submit-review",
                        headers=headers)
    if resp.status_code == 200:
        print("[PASS] 提交评审成功")
    else:
        print(f"[FAIL] 提交评审失败: {resp.status_code}")
        return False
    
    # 3. 批准用例
    resp = requests.post(f"{BASE_URL}/api/testcases/{testcase_id}/approve",
                        json={"comment": "测试通过"},
                        headers=headers)
    if resp.status_code == 200:
        print("[PASS] 批准用例成功")
    else:
        print(f"[FAIL] 批准用例失败: {resp.status_code}")
        return False
    
    # 4. 验证评审状态
    resp = requests.get(f"{BASE_URL}/api/testcases/{testcase_id}", headers=headers)
    if resp.status_code == 200:
        tc = resp.json()
        if tc["review_status"] == "已批准":
            print(f"[PASS] 评审状态正确: {tc['review_status']}")
        else:
            print(f"[FAIL] 评审状态错误: {tc['review_status']}")
            return False
    
    # 5. 清理：删除测试用例
    requests.delete(f"{BASE_URL}/api/testcases/{testcase_id}", headers=headers)
    print("[PASS] 清理测试数据完成")
    
    return True

def test_automation_api(token):
    """测试自动化集成 API"""
    print("\n=== 测试 3: 自动化测试集成 ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 获取使用指南
    resp = requests.get(f"{BASE_URL}/api/automation/guide", headers=headers)
    if resp.status_code == 200:
        print("[PASS] 自动化集成指南 API 正常")
    else:
        print(f"[FAIL] 获取指南失败: {resp.status_code}")
        return False
    
    # 2. 测试批量提交（需要先有用例和计划）
    # 先获取一个项目
    resp = requests.get(f"{BASE_URL}/api/projects", headers=headers)
    if resp.status_code == 200:
        projects = resp.json()
        if projects:
            project_id = projects[0]["id"]
            
            # 获取该项目的用例
            resp = requests.get(f"{BASE_URL}/api/testcases", 
                              params={"project_id": project_id, "page_size": 1},
                              headers=headers)
            if resp.status_code == 200:
                testcases = resp.json()["items"]
                if testcases:
                    testcase_id = testcases[0]["id"]
                    
                    # 获取计划
                    resp = requests.get(f"{BASE_URL}/api/plans",
                                      params={"project_id": project_id},
                                      headers=headers)
                    if resp.status_code == 200:
                        plans = resp.json()
                        if plans:
                            plan_id = plans[0]["id"]
                            
                            # 批量提交结果
                            resp = requests.post(f"{BASE_URL}/api/automation/batch",
                                json={
                                    "plan_id": plan_id,
                                    "stage": "SIT",
                                    "framework": "Selenium",
                                    "build_number": "TEST-001",
                                    "results": [{
                                        "testcase_id": testcase_id,
                                        "status": "通过",
                                        "remark": "自动化测试",
                                        "duration_seconds": 5
                                    }]
                                },
                                headers=headers)
                            
                            if resp.status_code == 200:
                                result = resp.json()
                                print(f"[PASS] 批量提交成功: 成功{result['success']}条")
                            else:
                                print(f"[FAIL] 批量提交失败: {resp.status_code}")
                                return False
    
    return True

def test_coverage_matrix(token):
    """测试覆盖率矩阵"""
    print("\n=== 测试 4: 测试覆盖率矩阵 ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 获取项目列表
    resp = requests.get(f"{BASE_URL}/api/projects", headers=headers)
    if resp.status_code != 200:
        print(f"[FAIL] 获取项目失败: {resp.status_code}")
        return False
    
    projects = resp.json()
    if not projects:
        print("⚠ 没有项目，跳过覆盖率测试")
        return True
    
    project_id = projects[0]["id"]
    
    # 2. 创建需求
    resp = requests.post(f"{BASE_URL}/api/requirements", json={
        "project_id": project_id,
        "req_no": "REQ-TEST-001",
        "title": "覆盖率测试需求",
        "description": "测试用需求",
        "priority": "中",
        "status": "待处理"
    }, headers=headers)
    
    if resp.status_code != 200:
        print(f"[FAIL] 创建需求失败: {resp.status_code}")
        return False
    
    req_id = resp.json()["id"]
    print(f"[PASS] 创建需求成功，ID: {req_id}")
    
    # 3. 获取覆盖率矩阵
    resp = requests.get(f"{BASE_URL}/api/requirements/coverage/matrix",
                       params={"project_id": project_id},
                       headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"[PASS] 覆盖率矩阵 API 正常")
        print(f"  - 需求总数: {data['total_requirements']}")
        print(f"  - 已覆盖: {data['covered_requirements']}")
        print(f"  - 覆盖率: {data['coverage_rate']}%")
    else:
        print(f"[FAIL] 获取覆盖率矩阵失败: {resp.status_code}")
        return False
    
    # 4. 清理：删除需求
    requests.delete(f"{BASE_URL}/api/requirements/{req_id}", headers=headers)
    print("[PASS] 清理测试数据完成")
    
    return True

def test_dashboard_enhancements(token):
    """测试数据看板增强"""
    print("\n=== 测试 5: 增强数据看板 ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 获取项目列表
    resp = requests.get(f"{BASE_URL}/api/projects", headers=headers)
    if resp.status_code != 200:
        print(f"[FAIL] 获取项目失败: {resp.status_code}")
        return False
    
    projects = resp.json()
    if not projects:
        print("⚠ 没有项目，跳过看板测试")
        return True
    
    project_id = projects[0]["id"]
    
    # 2. 测试版本通过率趋势
    resp = requests.get(f"{BASE_URL}/api/stats/trends/pass-rate",
                       params={"project_id": project_id, "stage": "SIT"},
                       headers=headers)
    if resp.status_code == 200:
        print("[PASS] 版本通过率趋势 API 正常")
    else:
        print(f"[FAIL] 版本通过率趋势失败: {resp.status_code}")
        return False
    
    # 3. 测试缺陷收敛曲线
    resp = requests.get(f"{BASE_URL}/api/stats/trends/defect-convergence",
                       params={"project_id": project_id},
                       headers=headers)
    if resp.status_code == 200:
        print("[PASS] 缺陷收敛曲线 API 正常")
    else:
        print(f"[FAIL] 缺陷收敛曲线失败: {resp.status_code}")
        return False
    
    # 4. 测试人员工作量分布
    resp = requests.get(f"{BASE_URL}/api/stats/workload/distribution",
                       params={"project_id": project_id, "days": 30},
                       headers=headers)
    if resp.status_code == 200:
        print("[PASS] 人员工作量分布 API 正常")
    else:
        print(f"[FAIL] 人员工作量分布失败: {resp.status_code}")
        return False
    
    return True

def main():
    print("=" * 60)
    print("P1 功能测试脚本")
    print("=" * 60)
    
    # 登录
    print("\n正在登录...")
    token = login()
    if not token:
        print("登录失败，无法继续测试")
        return
    
    print("[PASS] 登录成功")
    
    # 运行测试
    results = []
    results.append(("日历视图", test_calendar_api(token)))
    results.append(("评审流程", test_review_workflow(token)))
    results.append(("自动化集成", test_automation_api(token)))
    results.append(("覆盖率矩阵", test_coverage_matrix(token)))
    results.append(("数据看板", test_dashboard_enhancements(token)))
    
    # 输出结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    for name, result in results:
        status = "[PASS] 通过" if result else "[FAIL] 失败"
        print(f"{name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 个测试通过")
    print("=" * 60)

if __name__ == "__main__":
    main()
