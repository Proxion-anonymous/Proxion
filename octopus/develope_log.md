1. function ssa_stack_memory_storage_flow_instruction ,add real mem and storage calculate

2. add callinfo param to the function emulate,witch include calldata and callvalue

3. Change the JUMP logical , keep going only while condition is True

4. Change the state copy , do not deep copy a state when jump

5. Change the emulate function, do an state init at the beginning