## AI tool used: Claude.
# 1. prompt:
The storyline
A busy clinic with a few doctors. The front desk books patients into time slots, but keeps double-booking a doctor or letting two patients grab the same slot. Patients cancel — if they cancel in good time it’s free, but a late cancellation should carry a small fee. The desk needs to see a doctor’s day, find a patient’s appointment by name, and never let two appointments for the same doctor overlap.
Build the front desk something so no doctor is ever double-booked and late cancellations are handled fairly.
(The desk’s frustrations are the spec — build it for any clinic. Get conflict-free booking and the cancellation rule right first, then the lookups.)
generate a SQLite database schema that accommodates the twist, user registration, and search features.
# 2. prompt:
 Write the initialization script to create tables for users and your core problem entity.
 # 3. prompt: 
 give the structural pipeline to create this project. in detail.
 # 4.prompt:
 Act as an expert backend developer. I need you to implement the REST APIs for an Express.js and SQLite3 application. Follow these instructions precisely:

1. Create a registration endpoint (POST /api/register) and a login endpoint (POST /api/login). Use bcryptjs to securely hash passwords and jsonwebtoken (JWT) to return a signed token upon successful login.
2. Build the core appointment booking endpoint (POST /api/appointments). Implement strict validation logic to ensure that a doctor cannot be double-booked. No two appointments for the same doctor_id should ever overlap in time.
3. Build a cancellation endpoint (PUT /api/appointments/:id/cancel). Calculate the difference between the current time and the appointment's start_time. If it's less than 24 hours away, update the status to 'cancelled_fee' and apply a flat $25 late cancellation fee. If it's more than 24 hours away, set the status to 'cancelled_free' with a $0 fee.
4. Build a query endpoint (GET /api/appointments) that retrieves all bookings. It MUST support the following mandatory features:
   - Search: filter results using a SQL LIKE statement against patient_name.
   - Sorting: allow ordering by start_time or patient_name in either ASC or DESC order.
   - Pagination: enforce page limits and offsets using a limit and offset calculation based on a query parameter.
5. Provide a GET /api/doctors endpoint to fetch the master list of seeded doctors.

Provide the complete, production-ready server.js and database.js code blocks without leaving out any logic.
# 5. prompt:
Act as an expert frontend engineer. I need a single-file user interface (index.html) built with vanilla HTML5, JavaScript, and styled beautifully using Tailwind CSS via CDN. The file must contain three distinct logical views:

1. Mandatory Product Landing Page: A highly prominent, clean hero area explaining what the product is (MediSched), its target audience (clinic front-desk staff), how it helps eliminate scheduling chaos, and a designated section listing 3 future roadmap features (Automated SMS reminders, AI waitlist clearing, and multi-resource tracking).
2. Authentication Card: A clean login/registration toggle panel. It must securely save the returned JWT token to localStorage upon successful login and reveal the main workspace.
3. Front Desk Workspace Dashboard: Visible only to authenticated users, containing:
   - A sidebar form to book a new appointment (selecting a doctor, entering patient name, and selecting start/end date-times).
   - A central data table showing the active clinic calendar matrix.
   - Real-time interaction controls: A live search bar for patient names, a dropdown to filter by doctor, and a dropdown to change sorting order.
   - Working pagination buttons (Previous/Next) at the bottom.

Write the frontend JavaScript using the native Fetch API to communicate cleanly with the backend endpoints on localhost:3000. Ensure error messages (like double-booking alerts) are visually popped up using clean alert messages or UI alerts. Provide the full code.

# 6. prompt: 
provide with the commands to execute it in github codespace,
# 7. prompt: 
Twists for this problem
Level 1 — T6 (lifecycle): “Reschedule an appointment to a new time; it must stay conflict-free (re-check overlap) and keep the same patient and doctor.”
Level 2 — T1 (integrate): “Each morning, remind patients of today’s appointments via the Notification Service.” Graded via /outbox after POST /clock.
Level 3 — T2 (automation): “A job auto-marks appointments as no-show 30 min after their start if not completed.” Graded via POST /clock.
 update these problems.
 # 8. prompt:
 give the commands to update the repository.
# 9. prompt:
redesign the frontend to make it look more visually appealing.
# 10. prompt:
command to update it on github.