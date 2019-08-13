# TMACS #

Edit remote files with your editor of choice (vi or emacs), even if
TRAMP doesn't really work for you or if you ssh and su your way to a
network.

It works by tunneling the file-data through the terminal on which you
are working.

## Example ##

Start local emacs:
 $ emacs

In emacs, start the server:
 M-x server-start
 
In another terminal:
 $ tmacswrap    # this starts tmacswrap in your terminal

You should see a terminal title like tmacswrap(/home/user)

 # ssh a little bit around
 $ ssh you@this-server.de
 $ ssh youtoo@server2.companydomain
 $ ssh you@hard-to-reach-server.companydomain

 # su to some user
 $ su

On a this shell (it's build for bash) press Ctrl-t t. That should install
the 'tmacs' command as a function in your current shell session.

 $ tmacs -t some_text_file.txt   # this should open your local emacsclient
 
## Usage ##

C-t t : Installs the tmacs command

 # starts local emacsclient to use with tramp
 $ tmacs <file>
 
 # tunnels file through terminal and starts local emacsclient
 # this is the really useful thing, if tramp is not a real option
 $ tmacs -t <file>
 
## Customize ##

You are probably using vi or some other weird non-emacs-editor, but
this tool should be relatively easy to customize. Just find the
calls to emacsclient and change them to use your editor.
