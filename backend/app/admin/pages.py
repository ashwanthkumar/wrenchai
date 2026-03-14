"""NiceGUI admin pages: login, dashboard, and browse."""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from nicegui import app, ui
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.config import settings
from app.db.models import Admin, Manual, ManualStatus
from app.db.seed import verify_password
from app.services.pdf_processor import process_pdf
from app.services.rag import RAGService


def setup_admin_pages(
    db_session_factory: async_sessionmaker,
    rag_service: RAGService,
) -> None:
    """Register all NiceGUI admin pages."""

    def is_authenticated() -> bool:
        return app.storage.user.get("authenticated", False)

    # ── Login page ──────────────────────────────────────────────────────

    @ui.page("/admin/login")
    async def login_page():
        async def try_login():
            username = username_input.value
            password = password_input.value

            async with db_session_factory() as db:
                result = await db.execute(
                    select(Admin).where(Admin.username == username)
                )
                admin = result.scalar_one_or_none()

            if admin and verify_password(password, admin.password_hash):
                app.storage.user["authenticated"] = True
                app.storage.user["username"] = username
                ui.navigate.to("/admin/")
            else:
                ui.notify("Invalid credentials", type="negative")

        with ui.card().classes("absolute-center w-96"):
            ui.label("WrenchAI Admin").classes("text-2xl font-bold mb-4")
            username_input = ui.input("Username").classes("w-full")
            password_input = ui.input("Password", password=True).classes("w-full")
            ui.button("Login", on_click=try_login).classes("w-full mt-4")

    # ── Dashboard page ──────────────────────────────────────────────────

    @ui.page("/admin/")
    async def dashboard_page():
        if not is_authenticated():
            ui.navigate.to("/admin/login")
            return

        ui.label("WrenchAI Dashboard").classes("text-2xl font-bold mb-4")
        ui.button("Browse Manuals", on_click=lambda: ui.navigate.to("/admin/browse"))
        ui.button(
            "Logout",
            on_click=lambda: (
                app.storage.user.clear(),
                ui.navigate.to("/admin/login"),
            ),
        ).classes("ml-2")

        ui.separator()
        ui.label("Upload Manual").classes("text-xl font-bold mt-4")

        car_make = ui.input("Car Make").classes("w-64")
        car_model = ui.input("Car Model").classes("w-64")
        car_year = ui.number("Car Year", value=2024, format="%.0f").classes("w-64")

        async def handle_upload(e):
            if not e.content:
                ui.notify("No file selected", type="warning")
                return

            manual_id = str(uuid.uuid4())
            upload_dir = Path(settings.upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)

            filename = e.name
            file_path = upload_dir / f"{manual_id}_{filename}"
            file_path.write_bytes(e.content.read())

            # Create manual record
            async with db_session_factory() as db:
                manual = Manual(
                    id=manual_id,
                    filename=filename,
                    car_make=car_make.value or "Unknown",
                    car_model=car_model.value or "Unknown",
                    car_year=int(car_year.value or 2024),
                    status=ManualStatus.pending,
                    created_at=datetime.utcnow(),
                )
                db.add(manual)
                await db.commit()

            ui.notify(f"Uploaded {filename}, processing started...", type="positive")

            # Trigger background processing
            async def run_processing():
                async with db_session_factory() as db:
                    await process_pdf(
                        file_path=str(file_path),
                        manual_id=manual_id,
                        rag_service=rag_service,
                        db=db,
                    )

            asyncio.create_task(run_processing())

        ui.upload(
            label="Upload PDF Manual",
            on_upload=handle_upload,
            auto_upload=True,
        ).props("accept=.pdf").classes("w-full mt-2")

        # ── Status table ────────────────────────────────────────────────

        ui.separator()
        ui.label("Processing Status").classes("text-xl font-bold mt-4")

        table_container = ui.column().classes("w-full")

        async def refresh_table():
            table_container.clear()
            async with db_session_factory() as db:
                result = await db.execute(
                    select(Manual).order_by(Manual.created_at.desc())
                )
                manuals = result.scalars().all()

            with table_container:
                if not manuals:
                    ui.label("No manuals uploaded yet.")
                    return

                columns = [
                    {"name": "filename", "label": "Filename", "field": "filename"},
                    {"name": "car", "label": "Car", "field": "car"},
                    {"name": "status", "label": "Status", "field": "status"},
                    {"name": "chunks", "label": "Chunks", "field": "chunks"},
                    {"name": "error", "label": "Error", "field": "error"},
                ]
                rows = [
                    {
                        "filename": m.filename,
                        "car": f"{m.car_year} {m.car_make} {m.car_model}",
                        "status": m.status.value,
                        "chunks": m.chunk_count or "-",
                        "error": m.error_message or "",
                    }
                    for m in manuals
                ]
                ui.table(columns=columns, rows=rows).classes("w-full")

        await refresh_table()
        ui.timer(5.0, refresh_table)

    # ── Browse page ─────────────────────────────────────────────────────

    @ui.page("/admin/browse")
    async def browse_page():
        if not is_authenticated():
            ui.navigate.to("/admin/login")
            return

        ui.label("Browse Manuals").classes("text-2xl font-bold mb-4")
        ui.button("Back to Dashboard", on_click=lambda: ui.navigate.to("/admin/"))

        ui.separator()

        # List completed manuals
        async with db_session_factory() as db:
            result = await db.execute(
                select(Manual).where(Manual.status == ManualStatus.completed)
            )
            manuals = result.scalars().all()

        if not manuals:
            ui.label("No completed manuals yet.")
            return

        for manual in manuals:
            with ui.expansion(
                f"{manual.car_year} {manual.car_make} {manual.car_model} — {manual.filename}",
            ).classes("w-full"):
                # Show markdown content
                md_path = Path(settings.processed_dir) / f"{manual.id}.md"
                if md_path.exists():
                    content = md_path.read_text()
                    # Show first 2000 chars to avoid overwhelming the UI
                    display = content[:2000]
                    if len(content) > 2000:
                        display += "\n\n... (truncated)"
                    ui.markdown(display)
                else:
                    ui.label("Processed markdown not found.")

        # RAG search test
        ui.separator()
        ui.label("Test RAG Search").classes("text-xl font-bold mt-4")

        search_query = ui.input("Search query").classes("w-full")
        results_container = ui.column().classes("w-full")

        async def do_search():
            results_container.clear()
            query = search_query.value
            if not query:
                ui.notify("Enter a search query", type="warning")
                return

            results = rag_service.search(query=query, top_k=5)
            with results_container:
                if not results:
                    ui.label("No results found.")
                else:
                    for r in results:
                        with ui.card().classes("w-full mb-2"):
                            ui.label(f"Distance: {r['distance']:.4f}").classes(
                                "text-sm text-gray-500"
                            )
                            ui.markdown(r["text"][:500])

        ui.button("Search", on_click=do_search).classes("mt-2")
