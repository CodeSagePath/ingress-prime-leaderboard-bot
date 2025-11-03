#!/usr/bin/env python3
"""
Simple test script to verify the syntax of leaderboard.py file.
This avoids importing dependencies and just checks for syntax errors.
"""

import ast
import sys
import os

def check_syntax(file_path):
    """Check if a Python file has valid syntax."""
    try:
        with open(file_path, 'r') as f:
            source = f.read()
        
        # Parse the source code into an AST
        ast.parse(source, filename=file_path)
        return True, "Syntax is valid"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def check_specific_functions(file_path):
    """Check if specific functions exist in the file."""
    try:
        with open(file_path, 'r') as f:
            source = f.read()
        
        # Parse the source code into an AST
        tree = ast.parse(source)
        
        # Find all function definitions
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        
        # Check if get_leaderboard function exists
        if 'get_leaderboard' in functions:
            return True, "get_leaderboard function found", functions
        else:
            return False, "get_leaderboard function not found", functions
    except Exception as e:
        return False, f"Error checking functions: {e}", []

def check_sqlite_specific_changes(file_path):
    """Check if SQLite-specific changes have been made."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for PostgreSQL-specific functions that should be replaced
        postgresql_functions = ['jsonb_object_agg', 'jsonb_each']
        sqlite_functions = ['json_group_object', 'json_each']
        
        postgresql_found = any(func in content for func in postgresql_functions)
        sqlite_found = any(func in content for func in sqlite_functions)
        
        return {
            "postgresql_functions_found": postgresql_found,
            "sqlite_functions_found": sqlite_found,
            "content": content
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    file_path = "bot/services/leaderboard.py"
    
    # Test 1: Check syntax
    syntax_valid, syntax_msg = check_syntax(file_path)
    print(f"1. Syntax check: {'✅ PASSED' if syntax_valid else '❌ FAILED'} - {syntax_msg}")
    
    # Test 2: Check for specific functions
    func_valid, func_msg, functions = check_specific_functions(file_path)
    print(f"2. Function check: {'✅ PASSED' if func_valid else '❌ FAILED'} - {func_msg}")
    print(f"   Functions found: {', '.join(functions)}")
    
    # Test 3: Check for SQLite-specific changes
    changes = check_sqlite_specific_changes(file_path)
    if "error" in changes:
        print(f"3. SQLite changes check: ❌ ERROR - {changes['error']}")
    else:
        print(f"3. SQLite changes check:")
        print(f"   PostgreSQL functions found: {'✅ YES' if changes['postgresql_functions_found'] else '✅ NO'}")
        print(f"   SQLite functions found: {'✅ YES' if changes['sqlite_functions_found'] else '❌ NO'}")
        
        # Additional check: Look for the specific fix in the code
        if 'json_group_object' in changes['content'] and 'json_each' in changes['content']:
            print("   ✅ SQLite-specific JSON functions found in the code")
        else:
            print("   ❌ SQLite-specific JSON functions not found in the code")
    
    # Overall result
    overall_success = syntax_valid and func_valid
    print(f"\nOverall result: {'✅ PASSED' if overall_success else '❌ FAILED'}")
    
    if not overall_success:
        sys.exit(1)