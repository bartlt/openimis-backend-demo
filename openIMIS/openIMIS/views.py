from django.http import HttpResponse
from .dataloaders import get_dataloaders
from . import tracer

from graphene_django.constants import MUTATION_ERRORS_FLAG
from graphene_django.utils.utils import set_rollback
from graphql_jwt.exceptions import JSONWebTokenError
from graphene_django.views import GraphQLView as BaseGraphQLView, HttpError
from graphql.pyutils import Path
from graphql_sync_dataloaders import DeferredExecutionContext
import logging

logger = logging.getLogger(__name__)


def has_jwt_error(errors):
    for error in errors:
        if isinstance(getattr(error, "original_error", None), JSONWebTokenError):
            return True
    return False


def is_request_error(errors):
    # Syntax/validation errors and errors raised outside resolvers carry no path:
    # graphql-core 3's equivalent of graphql-core 2's `ExecutionResult.invalid`.
    return any(not getattr(error, "path", None) for error in errors)


class SyncDataLoaderExecutionContext(DeferredExecutionContext):
    """
    Lets the synchronous DataLoaders (core.dataloaders) batch their loads.

    graphql-sync-dataloaders 0.1.1 calls ``handle_field_error(error, return_type)``,
    but graphql-core >= 3.2.4 also expects the field ``path``; rebuild it from the
    located error so field errors are collected instead of failing the request.
    """

    def handle_field_error(self, error, return_type, path=None):
        if path is None:
            for key in error.path or ():
                path = Path(path, key, None)
        return super().handle_field_error(error, return_type, path)


class GraphQLView(BaseGraphQLView):
    execution_context_class = SyncDataLoaderExecutionContext

    def json_encode(self, request, d, pretty=False):
        with tracer.trace(op="GraphQLView.json_encode"):
            return super().json_encode(request, d, pretty=pretty)

    def _get_response(self, request, data, show_graphiql=False):
        query, variables, operation_name, id = self.get_graphql_params(request, data)

        execution_result = self.execute_graphql_request(
            request, data, query, variables, operation_name, show_graphiql
        )

        if getattr(request, MUTATION_ERRORS_FLAG, False) is True:
            set_rollback()

        status_code = 200
        if execution_result:
            response = {}

            if execution_result.errors:
                set_rollback()
                response["errors"] = [
                    self.format_error(e) for e in execution_result.errors
                ]
                # status_code = 500 per spec GQL must return 200 even for error

            if execution_result.errors and is_request_error(execution_result.errors):
                status_code = 400
            elif execution_result.errors and has_jwt_error(execution_result.errors):
                status_code = 401
            else:
                response["data"] = execution_result.data

            if self.batch:
                response["id"] = id
                response["status"] = status_code

            result = self.json_encode(request, response, pretty=show_graphiql)
        else:
            result = None

        return result, status_code

    def get_response(self, request, data, show_graphiql=False):
        with tracer.trace(op="GraphQLView.get_response") as span:
            result, status_code = self._get_response(
                request, data, show_graphiql=show_graphiql
            )
            span.set_tag("status_code", status_code)
        return result, status_code

    def get_context(self, request):
        request.dataloaders = get_dataloaders()
        return request

    def parse_body(self, request):
        with tracer.trace(op="GraphQLView.parse_body") as span:
            request_json = super().parse_body(request)
            span.set_data("Body", request_json)
            return request_json

    def execute_graphql_request(
        self, request, data, query, variables, operation_name, show_graphiql=False
    ):
        if not request or getattr(request, "content_type", "") != "application/json":
            raise HttpError(HttpResponse(
                "Unsupported Media Type: The server only accepts application/json requests.",
                status=415,
            ))
        with tracer.trace(op="document.execute"):
            return super().execute_graphql_request(
                request, data, query, variables, operation_name, show_graphiql
            )


class OpenIMISGraphQLView(GraphQLView):
    def execute_graphql_request(self, *args, **kwargs):
        """Extract any exceptions and send them to Sentry"""
        result = super().execute_graphql_request(*args, **kwargs)
        if result.errors:
            self._capture_sentry_exceptions(result.errors)
        return result

    def _capture_sentry_exceptions(self, errors):
        for error in errors:
            try:
                logger.error(error.original_error)
            except AttributeError:
                logger.error(error)
