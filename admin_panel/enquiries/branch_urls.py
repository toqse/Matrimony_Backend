from django.urls import path

from .branch_views import (
    BranchEnquiryAddNoteView,
    BranchEnquiryDetailView,
    BranchEnquiryListCreateView,
    BranchEnquiryMoveView,
    BranchEnquiryReassignView,
    BranchEnquirySummaryView,
)

urlpatterns = [
    path("summary/", BranchEnquirySummaryView.as_view(), name="branch-enquiry-summary"),
    path("", BranchEnquiryListCreateView.as_view(), name="branch-enquiry-list-create"),
    path("<int:pk>/", BranchEnquiryDetailView.as_view(), name="branch-enquiry-detail"),
    path("<int:pk>/reassign/", BranchEnquiryReassignView.as_view(), name="branch-enquiry-reassign"),
    path("<int:pk>/move/", BranchEnquiryMoveView.as_view(), name="branch-enquiry-move"),
    path("<int:pk>/notes/", BranchEnquiryAddNoteView.as_view(), name="branch-enquiry-notes"),
]
