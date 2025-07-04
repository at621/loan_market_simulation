import pandas as pd

# Test boolean filtering issue
data = [
    {"bank_id": "B05", "is_active": True, "amount": 100},
    {"bank_id": "B05", "is_active": True, "amount": 200},
    {"bank_id": "B05", "is_active": False, "amount": 300},
]

df = pd.DataFrame(data)
print("DataFrame:")
print(df)
print(f"\nis_active dtype: {df['is_active'].dtype}")

# Test different filtering approaches
print("\nFilter 1: is_active == True")
f1 = df[df["is_active"] == True]
print(f"Results: {len(f1)} rows")

print("\nFilter 2: is_active")
f2 = df[df["is_active"]]
print(f"Results: {len(f2)} rows")

print("\nFilter 3: Combined with bank_id")
f3 = df[(df["bank_id"] == "B05") & (df["is_active"] == True)]
print(f"Results: {len(f3)} rows")

# Test with different boolean representations
data2 = [
    {"bank_id": "B05", "is_active": "True", "amount": 100},
    {"bank_id": "B05", "is_active": "True", "amount": 200},
]
df2 = pd.DataFrame(data2)
print(f"\nString 'True' test - is_active dtype: {df2['is_active'].dtype}")
f4 = df2[df2["is_active"] == True]
print(f"String == True results: {len(f4)} rows")
f5 = df2[df2["is_active"] == "True"]
print(f"String == 'True' results: {len(f5)} rows")