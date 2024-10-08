from django.shortcuts import render, redirect, get_object_or_404  # type: ignore
from django.http import JsonResponse  # type: ignore
from .models import Room_Status, Room, Booking, Status
import json
from datetime import datetime
import requests  # type: ignore
from django.contrib import messages
from company_department.models import Company
from .forms import RoomForm


def booking(request):
    context = {"url": "booking"}
    if request.user.is_authenticated:
        if request.method == "POST":
            date = request.POST.get("date")
            start_time = request.POST.get("start_time")
            end_time = request.POST.get("end_time")

            # Convert the input date and times to datetime objects
            start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
            end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

            # Query for rooms that are not booked during the specified time range
            booked_rooms = (
                # sequence 0 = Waiting, sequence 2 = Rejected, sequence 3 = Canceled
                Booking.objects.exclude(status__sequence__in=[0, 2, 3])
                .filter(start_date__lt=end_datetime, end_date__gt=start_datetime)
                .values_list("room_id", flat=True)
            )

            available_rooms = (
                Room.objects.filter(company=request.user.fccorp, status__name="Active")
                .exclude(id__in=booked_rooms)
                .order_by("sequence")
            )

            context.update(
                {
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "rooms": available_rooms,
                }
            )

            return render(request, "room/booking/index.html", context)
        else:
            return render(request, "room/booking/index.html", context)
    else:
        return redirect("/")


def dashboard(request):
    context = {"url": "dashboard"}
    if request.user.is_authenticated:
        rooms = Room.objects.filter(company=request.user.fccorp)
        context.update({"rooms": rooms})
        if request.method == "POST":
            room_id = request.POST.get("room_id")

            # Fetch selected room and bookings
            selectedRoom = Room.objects.get(id=room_id)
            bookings = Booking.objects.filter(
                room__id=room_id,
                status__sequence__in=[
                    1,
                    4,
                ],  # sequence 1 = Approved, sequence 4 = Confirmed
            )

            bookings_data = []
            for booking in bookings:
                bookings_data.append(
                    {
                        "id": booking.pk,
                        "emp_id": booking.employee.emp_id,
                        "first_name": booking.employee.first_name,
                        "last_name": booking.employee.last_name,
                        "title": booking.title,
                        "start_date": booking.start_date.isoformat(),
                        "end_date": booking.end_date.isoformat(),
                        "description": booking.description.replace(
                            "\r\n", "<br>"
                        ).replace(
                            "\n", "<br>"
                        ),  # แปลง \r\n และ \n เป็น <br>
                        "status": booking.status.name,
                        "color": booking.status.color,
                        "remark": booking.remark.replace("\r\n", "<br>").replace(
                            "\n", "<br>"
                        ),  # แปลง \r\n และ \n เป็น <br>,
                    }
                )

            # Update context with selected room, its bookings, and serialized bookings data
            context.update(
                {
                    "bookings": json.dumps(
                        bookings_data
                    ),  # Ensure that bookings are JSON string
                    "selectedRoom": selectedRoom,
                }
            )
            return render(request, "room/dashboard/index.html", context)
        else:
            return render(request, "room/dashboard/index.html", context)
    else:
        return redirect("/")


def save_booking(request):
    if request.method == "POST":
        try:
            data = request.POST
            title = data.get("title")
            description = data.get("description")
            date = data.get("date")
            start_time = data.get("start_time")
            end_time = data.get("end_time")
            room_id = data.get("room_id")

            try:
                room = Room.objects.get(id=room_id)
            except Room.DoesNotExist:
                return JsonResponse(
                    {"status": "Room not found."},
                    status=404,
                )

            if start_time > end_time:
                return JsonResponse(
                    {"status": "Start time cannot be later than end time."},
                    status=400,
                )
            # Convert the input date and times to datetime objects
            start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
            end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")

            # Check if the start date is in the past
            today = datetime.now().date()
            start_date = start_datetime.date()
            if start_date < today:
                return JsonResponse(
                    {"status": "Cannot book a room for a past date."},
                    status=400,
                )

            if start_datetime == end_datetime:
                return JsonResponse(
                    {"status": "Start date and end date cannot be the same."},
                    status=400,
                )

            # Check if there are any bookings with status sequence 1 during the requested time period
            conflicting_bookings = Booking.objects.filter(
                room=room,
                status__sequence__in=[
                    1,
                    4,
                ],  # sequence 1 = Approved, sequence 4 = Confirmed
                start_date__lt=end_datetime,
                end_date__gt=start_datetime,
            )
            if conflicting_bookings.exists():
                return JsonResponse(
                    {"status": "The selected time slot is not available."},
                    status=400,
                )

            employee = request.user
            status = Status.objects.get(sequence=1)  # sequence 1 is Approved

            # Save the booking
            booking = Booking.objects.create(
                room=room,
                employee=employee,
                title=title,
                description=description,
                start_date=start_datetime,
                end_date=end_datetime,
                status=status,
            )

            # Send Line Notify
            line_notify_token = request.user.fccorp.line_notify_room
            line_notify_url = "https://notify-api.line.me/api/notify"
            headers = {"Authorization": f"Bearer {line_notify_token}"}

            message = (
                f"\nBooking ID: {booking.id}\n"
                f"Room: {booking.room.name}\n"
                f"Title: {booking.title}\n"
                f"Requester: {booking.employee.first_name} {booking.employee.last_name}\n"
                f"Description: {booking.description}\n"
                f"Tel: {booking.employee.tel}\n"
                f"Start: {booking.start_date.strftime('%d/%m/%Y %H:%M')}\n"
                f"End: {booking.end_date.strftime('%d/%m/%Y %H:%M')}\n"
                f"Status: {booking.status.name}"
            )
            payload = {"message": message}

            response = requests.post(line_notify_url, headers=headers, data=payload)
            if response.status_code != 200:
                return JsonResponse(
                    {"status": "Booking saved, but failed to send Line notification."},
                    status=200,
                )
            else:
                return JsonResponse(
                    {
                        "status": "Booking saved and Line notification sent successfully!"
                    },
                    status=200,
                )

        except Exception as e:
            print(f"Unexpected error: {e}")
            return JsonResponse(
                {"status": f"An unexpected error occurred: {str(e)}"},
                status=500,
            )

    return JsonResponse({"status": "Invalid request"}, status=400)


def cancel_booking(request):
    if request.method == "POST":
        booking_id = request.POST.get("id")
        remark = request.POST.get("remark")  # รับค่าหมายเหตุจากคำขอ

        # ดึงข้อมูลการจองตาม booking_id และตรวจสอบว่าผู้ใช้เป็นเจ้าของ
        booking = get_object_or_404(Booking, id=booking_id, employee=request.user)

        # ตั้งสถานะเป็น "Canceled"
        booking.status = Status.objects.get(sequence=3)
        booking.remark = remark  # บันทึกหมายเหตุใน Booking
        booking.save()

        return JsonResponse({"success": True})

    return JsonResponse(
        {"success": False, "error": "Invalid request method"}, status=400
    )


def history(request):
    if request.user.is_authenticated:
        user_id = request.user.id
        user_company = request.user.fccorp
        bookings = Booking.objects.filter(
            room__company=user_company, employee__id=user_id
        )
        statuses = Status.objects.all().order_by("sequence")
        rooms = Room.objects.filter(company=request.user.fccorp).order_by("sequence")
        # Check if the start date is in the past
        today = datetime.now()

        context = {
            "bookings": bookings,
            "url": "history",
            "statuses": statuses,
            "rooms": rooms,
            "today": today,
        }
        return render(request, "room/history/index.html", context)
    else:
        return redirect("/")


def history_staff(request):

    # เคลียร์ข้อความก่อนเข้าสู่หน้า
    storage = messages.get_messages(request)
    for _ in storage:
        pass  # ลูปเพื่อเคลียร์ข้อความทั้งหมด

    if request.user.is_authenticated and request.user.is_staff:
        user_company = request.user.fccorp
        bookings = Booking.objects.filter(room__company=user_company)
        statuses = Status.objects.all().order_by("sequence")
        rooms = Room.objects.filter(company=request.user.fccorp).order_by("sequence")

        context = {
            "bookings": bookings,
            "url": "history_staff",
            "statuses": statuses,
            "rooms": rooms,
        }
        return render(request, "room/staff/history/index.html", context)
    else:
        return redirect("/")


def edit_booking(request):
    if request.user.is_authenticated and request.user.is_staff:
        if request.method == "POST":
            # Get the booking ID from the form data
            booking_id = request.POST.get("id")
            status_id = request.POST.get("status")
            remark = request.POST.get("remark")

            # Get the booking object by its ID
            booking = get_object_or_404(Booking, id=booking_id)

            # Get the status object by its ID
            status = get_object_or_404(Status, id=status_id)

            # Update the booking fields
            booking.status = status
            booking.remark = remark
            booking.save()

            # Add a success message
            messages.success(request, "การจองได้รับการแก้ไขเรียบร้อยแล้ว")

            # Redirect to the bookings page (or wherever you want after editing)
            return redirect(
                "room_history_staff"
            )  # Change 'bookings_history' to the appropriate URL name

    # If not POST, just redirect or handle accordingly
    return redirect("/")


def room_staff(request):
    context = {
        "url": "room_staff",
    }

    # เคลียร์ข้อความก่อนเข้าสู่หน้า
    storage = messages.get_messages(request)
    for _ in storage:
        pass  # ลูปเพื่อเคลียร์ข้อความทั้งหมด

    if request.user.is_authenticated and request.user.is_staff:
        rooms = Room.objects.filter(company=request.user.fccorp).order_by("sequence")
        statuses = Room_Status.objects.all()
        companies = Company.objects.filter(id=request.user.fccorp.id)

        if request.method == "POST":
            form = RoomForm(
                request.POST, request.FILES, user=request.user
            )  # ส่ง request.user ใน POST
            if form.is_valid():
                form.save()
                messages.success(request, "เพิ่มห้องประชุมสำเร็จ!")  # เพิ่มข้อความแจ้งเตือน
                return redirect("room_staff")
        else:
            form = RoomForm(user=request.user)  # ส่ง request.user ใน GET

        context.update(
            {"rooms": rooms, "statuses": statuses, "form": form, "companies": companies}
        )
        return render(request, "room/staff/room/index.html", context)
    else:
        return redirect("/")


def edit_room(request):
    if request.method == "POST":
        room_id = request.POST.get("id")
        room = get_object_or_404(Room, id=room_id)

        # อัปเดตข้อมูลทั่วไป
        room.name = request.POST.get("name")
        room.detail = request.POST.get("detail")
        room.remark = request.POST.get("remark")
        room.sequence = request.POST.get("sequence")
        room.status_id = request.POST.get("status")
        room.company_id = request.POST.get("company")

        # ตรวจสอบว่ามีการอัปโหลดภาพใหม่หรือไม่
        if "image" in request.FILES and request.FILES["image"]:
            room.image = request.FILES["image"]

        room.save()
        messages.success(request, "อัพเดทห้องประชุมสำเร็จ!")  # เพิ่มข้อความแจ้งเตือน

        return redirect("room_staff")


def delete_room(request):
    if (
        request.method == "POST"
        and request.user.is_authenticated
        and request.user.is_staff
    ):
        room_id = request.POST.get("id")
        try:
            room = Room.objects.get(id=room_id, company=request.user.fccorp)
            room.delete()
            return JsonResponse({"success": True})
        except Room.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "ห้องประชุมไม่พบหรือไม่มีสิทธิ์ในการลบ"}
            )
    return JsonResponse({"success": False, "message": "คำขอลบไม่ถูกต้อง"})


def confirm_booking(request, booking_id):
    context = {}
    if request.user.is_authenticated:
        user_id = request.user.id
        user_company = request.user.fccorp
        booking = Booking.objects.filter(
            room__company=user_company,
            employee__id=user_id,
            id=booking_id,
        ).first()

        if booking is None:
            context.update(
                {
                    "title": "เกิดข้อผิดพลาด",
                    "detail": "กรุณาเข้าสู่ระบบด้วยบัญชีที่ท่านได้ทำการจองห้องประชุม",
                    "image": "error",
                }
            )
        else:
            if booking.status.sequence == 1:
                status = get_object_or_404(Status, sequence=4)
                # ทำการยืนยันการเข้าห้องประชุม
                booking.status = status
                booking.save()
                context.update(
                    {
                        "title": "สำเร็จ",
                        "detail": "ยืนยันการเข้าห้องประชุมเสร็จสิ้น",
                        "image": "success",
                    }
                )
            else:
                context.update(
                    {
                        "title": "เกิดข้อผิดพลาด",
                        "detail": "ท่านเคยยืนยันการเข้าห้องประชุมนี้แล้ว",
                        "image": "error",
                    }
                )
        return render(request, "room/confirm_booking/index.html", context)
    else:
        return redirect("/")
