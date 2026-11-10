from django.urls import reverse

from .models import UserProfile, Workflow


def navigation_context(request):
    user = request.user
    workflow = None
    breadcrumbs = []
    if user.is_authenticated:
        try:
            if user.profile.role == UserProfile.ROLE_OFFICER:
                workflow = Workflow.objects.filter(user=user).first()
                stages = [
                    ("Upload Dataset", "upload"),
                    ("Data Preview", "data_preview"),
                    ("Preprocessing", "preprocess"),
                    ("Prediction", "predict"),
                    ("Results", "prediction_results"),
                    ("Visualization", "visualize"),
                    ("Reports", "reports"),
                    ("History", "history"),
                ]
                route_names = {
                    "dashboard": -1,
                    "upload": 0,
                    "data_preview": 1,
                    "preprocess": 2,
                    "predict": 3,
                    "prediction_results": 4,
                    "visualize": 5,
                    "reports": 6,
                    "report_preview": 6,
                    "download_page": 6,
                    "download_pdf": 6,
                    "download_excel": 6,
                    "history": 7,
                }
                current_index = route_names.get(
                    getattr(request.resolver_match, "url_name", ""), -1
                )
                completed = workflow.completed_stage if workflow else -1
                visible_through = max(completed + 1, current_index)
                for index, (label, route_name) in enumerate(stages):
                    if index <= visible_through:
                        breadcrumbs.append({
                            "label": label,
                            "url": reverse(route_name),
                            "current": index == current_index,
                        })
        except UserProfile.DoesNotExist:
            pass
    return {"current_workflow": workflow, "workflow_breadcrumbs": breadcrumbs}
