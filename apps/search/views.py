from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.permissions import IsEmployeeOrAbove
from apps.search.serializers import SearchQuerySerializer, SearchResultSerializer
from apps.search.services import hybrid_search


class SearchView(GenericAPIView):
    permission_classes = [IsEmployeeOrAbove]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"
    serializer_class = SearchQuerySerializer

    def get(self, request):
        query_serializer = self.get_serializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        results = hybrid_search(
            query=query_serializer.validated_data["q"],
            user=request.user,
            limit=query_serializer.validated_data["limit"],
        )
        return Response(SearchResultSerializer(results, many=True).data)