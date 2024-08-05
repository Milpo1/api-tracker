# %%
import sqlite3

# Connect to (or create) the database
conn = sqlite3.connect('instance/prices.db')

# Create a cursor object
cursor = conn.cursor()

# Query the database
cursor.execute('SELECT * FROM price')
rows = cursor.fetchall()

# Print out the results
for row in rows:
    print(row)

# Close the connection
conn.close()
