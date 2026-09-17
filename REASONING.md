## The Priority Order
I followed the project brief exactly as instructed. I focused on building the most critical business features first before moving on to the extra tools.
First: I built the core booking engine with a conflict checker.
Second: I added the logic for cancellation fees.
Last: I built the search, filter, and pagination features.
## The Doctor Overlap Rule:
To prevent double-booking a doctor, I used a specific mathematical rule. Two appointments overlap if one starts before the other ends, AND it ends after the other starts. If those two conditions are true, their time ranges cross, and the booking is blocked.
## The Cancellation Fee Rule:
This is a straightforward time check. If a patient cancels their appointment less than 24 hours before it starts, the system charges them a fee. If they cancel 24 hours or more in advance, it is completely free.
## Automatic Patient Creation:
To make things easier for the front desk, I made the system smart. When someone books an appointment, the system checks the patient's name and phone number. If they aren't in the database yet, the system automatically creates a new patient profile right then and there. This saves the staff from having to do a separate "add patient" step first.
## How the UI and API Talk to Each Other:
The web pages don't touch the database directly. Instead, the frontend uses JavaScript fetch() to talk to the JSON API endpoints (which I documented in the README). The API acts as the middleman—it handles the requests from the UI, does the actual reading and writing to the database, and sends the data back.
##  How I Tested It:
Instead of clicking through the website manually dozens of times, I wrote an automated script. The script automatically walks through the exact scenarios from the project brief:
1. It books a slot.
2. It tries to double-book that same slot (and verifies that it fails).
3. It books a non-overlapping slot (and verifies that it works).
4. It tests searching and viewing a doctor's daily schedule.
5. It tests cancelling early (free) versus cancelling late (fee).

## The Big Bug I Fixed:
I ran into a really interesting bug in my first version of the booking system. As a safety net, I was checking for scheduling conflicts twice: once right before creating the appointment, and a second time right before saving it to the database.
But the second check kept failing on the very first booking, even though the database was completely empty!
The issue: The code had already added the new appointment to the active database session. When the second check ran, it looked at the session, saw the appointment, and compared the new appointment against itself. It flagged it as a duplicate conflict.
 The fix: I fixed it by explicitly saving the row first so it could get a unique ID. Then, I updated the conflict checker to ignore any appointment that matched that specific ID.