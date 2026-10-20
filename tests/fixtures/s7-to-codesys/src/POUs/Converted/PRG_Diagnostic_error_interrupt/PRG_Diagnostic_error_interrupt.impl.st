DB_Plant.diagCount := DB_Plant.diagCount + 1;
// MIGRATION-TODO: использует «LADDR», объявление которой не перенесено (системный тип S7 HW_ANY не поддерживается)
//                 (стр. 81)
// "DB_Plant".diagLastLaddr := #LADDR;
DB_Plant.diagLastChannel := Channel;
DB_Plant.diagIoState := IO_State;
