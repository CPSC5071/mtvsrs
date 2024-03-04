from django.shortcuts import render, redirect, get_object_or_404
from django.db import connection
from .models import ShowTable, Movie, TvSeries, History, Watchlist, WatchlistShow
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
import ast
from django.contrib.auth.decorators import login_required

def register_user(request: HttpRequest) -> HttpResponse:

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            success_url = reverse("index")
            return HttpResponseRedirect(success_url)
    else:
        form = UserCreationForm()

    context = {"form": form}

    return render(request, "registration/registration_form.html", context)

# @login_required()
def home_page(request):
    user_id = 1

    # Using raw queries as syntax for Django ORM is new to me
    new_release_columns = ['Show_ID', 'Show_Name', 'Show_Description', 'Show_Type']
    new_release_query = """
        SELECT 
            st.Show_ID as Show_ID,
            unioned.Show_Name as Show_Name,
            unioned.Show_Description as Show_Description,
            unioned.Show_Type as Show_Type,
            unioned.Show_Release_Date as Show_Release_Date
        FROM
            (
                (SELECT
                    Movie_ID AS Show_ID,
                    Name AS Show_Name,
                    Description as Show_Description,
                    'Movie' AS Show_Type,
                    Release_Date AS Show_Release_Date
                FROM
                    Movie)

                UNION ALL

                (SELECT
                    TV_Series_ID AS Show_ID,
                    Name AS Show_Name,
                    Description as Show_Description,
                    'TV' AS Show_Type,
                    Release_Date AS Show_Release_Date
                FROM
                    TV_Series)
            ) AS unioned
        JOIN
            Show_Table st ON 
            (st.Movie_ID = unioned.Show_ID)
            OR 
            (st.TV_Series_ID = unioned.Show_ID)
        ORDER BY 
            Show_Release_Date DESC 
        LIMIT 10;
    """

    with connection.cursor() as cursor:
        cursor.execute(new_release_query)
        new_release_shows = cursor.fetchall()
        new_release_shows = [
            # exclude release date
            {new_release_columns[i]: value for i, value in enumerate(show[:-1])} for show in new_release_shows
        ]

    context = {
        'card_count': range(10),
        'user_id': user_id,
        'new_release_shows': new_release_shows
    }
    return render(request, "home.html", context)

# Create a pop up alert for no search result
def search_feature(request):
    if request.method == 'POST':
        search_query = request.POST.get('search_query', '')

        try:
            movie = Movie.objects.get(name__icontains=search_query)
            show_table = ShowTable.objects.get(movie_id=movie.movie_id)
            show_id = show_table.show_id
            return show_page(request, show_id)
        except Movie.DoesNotExist:
            pass

        try:
            tv_series = TvSeries.objects.get(name__icontains=search_query)
            show_table = ShowTable.objects.get(tv_series_id=tv_series.tv_series_id)
            show_id = show_table.show_id
            return show_page(request, show_id)
        except TvSeries.DoesNotExist:
            context={'error_message':'No search result, please check again'}
    return render(request, 'post_search.html', context)



def show_page(request, show_id):
    user_id = 1

    ### Show data ###
    show = get_object_or_404(ShowTable, pk=show_id)
    if show.movie_id:
        show = get_object_or_404(Movie, pk=show.movie_id)
        show_type = "Movie"
    else:
        show = get_object_or_404(TvSeries, pk=show.tv_series_id)
        show_type = "TV"
    # parse genre string into list, then concat them with just a comma
    show.genre = ', '.join(ast.literal_eval(show.genre))

    ### Reviews ###
    reviews = History.objects.filter(show_id=show_id).select_related('user_id').order_by('-review_date')[:5]

    ### Status distribution ###
    status_types = ['Planned', 'Watching', 'Completed', 'Dropped']
    # pass in show_id as parameter when executing query rather than string interpolation to prevent sql injection
    status_distribution_query = """
        SELECT
            Status, COUNT(*) as Count
        FROM
            WatchlistShow
        WHERE
            Show_ID = %s
        GROUP BY Status;
    """
    # if status is not in the query results, count should be 0, so init an empty dict first
    status_distribution = {status_type: 0 for status_type in status_types}

    ### Execute queries ###
    with connection.cursor() as cursor:
        cursor.execute(status_distribution_query, [show_id])
        for row in cursor.fetchall():
            status_distribution[row[0]] = row[1]

    ### Build context and return
    context = {
        'show': show,
        'show_type': show_type,
        'status_distribution': status_distribution,
        'reviews': reviews,
        'card_count': range(10),
        'user_id': user_id
    }

    return render(request, "show.html", context)

def my_list_page(request):
    user_id = 1
    shows = ShowTable.objects.filter(watchlist__user_id=user_id).distinct()
    print(shows)