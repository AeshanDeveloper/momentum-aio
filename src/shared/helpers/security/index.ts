// Imports
import bcrypt from "bcryptjs";

// Security Helpers
export function generateSessionKey(){
  
}

export async function hashString(string){
  return await bcrypt.hash(string, 12)
}

export async function comparePass(pp1, hp2){
  return await bcrypt.compare(pp1, hp2)
}

