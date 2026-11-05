from decimal import Decimal as D

from src.tools.calculator import Item, PolicyTerms, calculate_payable

CL = {
    "room_rent_cap": "4.2", "proportionate_deduction": "4.3", "copay": "5.1",
    "non_payable": "Annex-II", "sum_insured_cap": "3.1",
}


def rules(res):
    return {d.rule: d.amount for d in res.deductions}


def test_clean_approve():
    t = PolicyTerms(sum_insured=D(500000))
    items = [Item("room", D(10000)), Item("surgeon", D(40000)), Item("medicine", D(5000))]
    r = calculate_payable(items, t, room_days=2)
    assert r.status == "approve" and r.payable == D("55000.00") and r.deductions == []


def test_room_rent_cap_and_proportionate():
    # limit 5000/day, charged 8000/day for 3 days -> ratio 0.625
    t = PolicyTerms(sum_insured=D(1000000), room_rent_limit_per_day=D(5000), clause_ids=CL)
    items = [Item("room", D(24000)), Item("surgeon", D(80000)),
             Item("medicine", D(10000)), Item("implant", D(30000))]
    r = calculate_payable(items, t, room_days=3)
    d = rules(r)
    assert d["room_rent_cap"] == D("9000.00")
    assert d["proportionate_deduction"] == D("30000.00")   # 80000 * 0.375
    # medicine and implant are not proportionately reduced
    assert r.payable == D("15000") + D("50000") + D("10000") + D("30000")
    assert r.status == "partial"
    assert all(x.clause_id for x in r.deductions)


def test_consumables_removed():
    t = PolicyTerms(sum_insured=D(500000), clause_ids=CL)
    r = calculate_payable([Item("surgeon", D(20000)), Item("consumable", D(1500))], t)
    assert r.payable == D("20000.00") and rules(r)["non_payable"] == D("1500.00")


def test_sublimit_then_copay():
    t = PolicyTerms(sum_insured=D(500000), copay_pct=D(10), sublimits={"implant": D(50000)},
                    clause_ids={"copay": "5.1", "sublimit:implant": "6.2"})
    r = calculate_payable([Item("surgeon", D(50000)), Item("implant", D(80000))], t)
    # after sublimit: 50000 + 50000 = 100000, copay 10% = 10000
    assert rules(r)["sublimit"] == D("30000.00")
    assert r.payable == D("90000.00")


def test_deductible_before_copay():
    t = PolicyTerms(sum_insured=D(500000), deductible=D(10000), copay_pct=D(20))
    r = calculate_payable([Item("surgeon", D(60000))], t)
    assert r.payable == D("40000.00")  # (60000-10000)*0.8


def test_sum_insured_cap():
    t = PolicyTerms(sum_insured=D(100000), clause_ids=CL)
    r = calculate_payable([Item("surgeon", D(150000))], t)
    assert r.payable == D("100000.00") and rules(r)["sum_insured_cap"] == D("50000.00")


def test_remaining_sum_insured_overrides():
    t = PolicyTerms(sum_insured=D(500000))
    r = calculate_payable([Item("surgeon", D(80000))], t, remaining_sum_insured=D(30000))
    assert r.payable == D("30000.00")


def test_all_non_payable_is_reject():
    t = PolicyTerms(sum_insured=D(500000))
    r = calculate_payable([Item("consumable", D(900))], t)
    assert r.status == "reject" and r.payable == D("0.00")


def test_no_room_cap_when_within_limit():
    t = PolicyTerms(sum_insured=D(500000), room_rent_limit_per_day=D(5000))
    r = calculate_payable([Item("room", D(9000)), Item("surgeon", D(20000))], t, room_days=2)
    assert r.status == "approve"