import pytest
from services.saboteur.app.injector import ChaosInjector

def test_chaos_injector_seed_reproducibility():
    injector1 = ChaosInjector(seed=12345)
    sequence1 = [(injector1.should_inject_prompt(), injector1.should_drop_packet(), injector1.should_force_tool_503()) for _ in range(50)]

    injector2 = ChaosInjector(seed=12345)
    sequence2 = [(injector2.should_inject_prompt(), injector2.should_drop_packet(), injector2.should_force_tool_503()) for _ in range(50)]

    assert sequence1 == sequence2

def test_prompt_injection_poisoning():
    injector = ChaosInjector(seed=42)
    original = "Failed login from 203.0.113.7 x40"
    poisoned = injector.inject_prompt(original)
    
    assert original in poisoned
    assert len(poisoned) > len(original)

def test_chaos_disabled():
    injector = ChaosInjector(seed=100)
    injector.set_enabled(False)
    
    assert injector.should_inject_prompt() is False
    assert injector.should_drop_packet() is False
    assert injector.should_force_tool_503() is False
