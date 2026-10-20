TYPE E_Mode : (Off := 0, Auto := 1) INT; END_TYPE
FUNCTION_BLOCK FB_Case
VAR
    m : E_Mode;
END_VAR
m := E_Mode.Auto;
END_FUNCTION_BLOCK
